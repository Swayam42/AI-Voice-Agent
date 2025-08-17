from fastapi import FastAPI, HTTPException, File, UploadFile, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
from dotenv import load_dotenv
import assemblyai as aai
import requests
import json
from datetime import datetime
from pathlib import Path

load_dotenv()

from services.stt_service import resilient_transcribe, transcribe_audio_bytes  # noqa: E402
from services.tts_service import MurfTTSClient  # noqa: E402
from services.llm_service import GeminiClient, build_chat_prompt  # noqa: E402
from schemas.tts import (  # noqa: E402
    TextToSpeechRequest,
    TextToSpeechResponse,
    EchoResponse,
    ChatResponse,
    SimpleTranscriptionResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("voice-agent")

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in .env file")

gemini_key = os.getenv("GEMINI_API_KEY")
if not gemini_key:
    raise ValueError("GEMINI_API_KEY not found in .env file")

MURF_API_KEY = os.getenv("MURF_API_KEY")
if not MURF_API_KEY:
    raise ValueError("MURF_API_KEY not found in .env file")

app = FastAPI(title="AI Voice Agent", version="0.2.0")
tts_client = MurfTTSClient(MURF_API_KEY)
llm_client = GeminiClient()

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

CHAT_HISTORY: dict[str, list] = {}

active_connections: set[WebSocket] = set()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.add(ws)
    logger.info("Client connected (active=%d)", len(active_connections))

    # Save to uploads folder with timestamp
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    file_path = os.path.join(uploads_dir, f"recorded_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm")

    try:
        with open(file_path, "ab") as f:
            while True:
                data = await ws.receive_bytes()
                f.write(data)
                logger.info("Received %d bytes, saved to %s", len(data), file_path)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected, file saved at %s", file_path)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        active_connections.discard(ws)
        logger.info("WebSocket closed (active=%d)", len(active_connections))

@app.websocket("/ws/stream-audio")
async def stream_audio(ws: WebSocket):
    """Receive binary audio chunks (e.g., MediaRecorder blobs) and save to uploads.
    Client may optionally send a text frame 'END' to finalize early; otherwise file closes on disconnect.
    Sends JSON events: ready, progress, done, error.
    """
    await ws.accept()
    uploads_dir = Path(__file__).parent / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    filename = f"stream_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.webm"
    file_path = uploads_dir / filename
    total = 0
    # Create file immediately
    f = open(file_path, 'wb')
    logger.info("[stream] started -> %s", file_path)
    await ws.send_json({"type": "ready", "file": filename})
    try:
        while True:
            msg = await ws.receive()
            mtype = msg.get('type')
            if mtype == 'websocket.disconnect':
                logger.info("[stream] disconnect")
                break
            if 'bytes' in msg and msg['bytes']:
                chunk = msg['bytes']
                f.write(chunk)
                f.flush()
                total += len(chunk)
                if total % 120000 < len(chunk):  # ~every 120KB
                    try:
                        await ws.send_json({"type": "progress", "bytes": total})
                    except Exception:
                        pass
            elif 'text' in msg and msg['text'] is not None:
                text = msg['text'].strip()
                if text.upper() == 'END':
                    await ws.send_json({"type": "info", "message": "Stream ended"})
                    break
                else:
                    await ws.send_json({"type": "ack", "message": f"ignored: {text[:20]}"})
            else:
                await ws.send_json({"type": "warn", "message": f"unhandled frame keys {list(msg.keys())}"})
        await ws.send_json({"type": "done", "file": filename, "bytes": total})
        logger.info("[stream] done %s bytes=%d", filename, total)
    except Exception as e:
        logger.error("[stream] error: %s", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try: f.close()
        except Exception: pass
        try: await ws.close()
        except Exception: pass
        logger.info("[stream] closed %s bytes=%d", filename, total)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        return HTMLResponse(f"Error loading page: {str(e)}", status_code=500)

@app.post("/generate_audio", response_model=TextToSpeechResponse)
async def generate_audio(payload: TextToSpeechRequest):
    logger.info("TTS generate request: %s chars", len(payload.text))
    audio_url = tts_client.synthesize(payload.text, payload.voiceId)
    return TextToSpeechResponse(audio_url=audio_url)

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        file_content = await file.read()
        return {"filename": file.filename, "content_type": file.content_type, "size": len(file_content)}
    except Exception:
        raise HTTPException(status_code=500, detail="Upload failed")

@app.post("/transcribe/file", response_model=SimpleTranscriptionResponse)
async def transcribe_file(file: UploadFile = File(...)):
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty file")
    text = transcribe_audio_bytes(audio_data)
    return SimpleTranscriptionResponse(transcription=text)
    
@app.post("/tts/echo", response_model=EchoResponse)
async def tts_echo(file: UploadFile = File(...)):
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty file")
    text = resilient_transcribe(audio_data)
    if not text:
        raise HTTPException(status_code=400, detail="Empty transcription")
    audio_url = tts_client.synthesize(text, "en-US-charles")
    return EchoResponse(audio_url=audio_url, transcription=text)

def append_history(session_id: str, role: str, content: str) -> list:
    history = CHAT_HISTORY.setdefault(session_id, [])
    history.append({"role": role, "content": content})
    return history

@app.post("/agent/chat/{session_id}", response_model=ChatResponse)
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Invalid audio file")
    user_text = transcribe_audio_bytes(audio_bytes)
    if not user_text:
        raise HTTPException(status_code=400, detail="Empty transcription")
    history = append_history(session_id, "user", user_text)
    prompt = build_chat_prompt(history)
    logger.info("LLM prompt chars=%d session=%s", len(prompt), session_id)
    ai_reply = llm_client.generate(prompt)
    logger.info("LLM reply chars=%d session=%s", len(ai_reply or ''), session_id)
    append_history(session_id, "assistant", ai_reply)
    try:
        audio_url = tts_client.synthesize(ai_reply, "en-US-ken")
    except HTTPException as e:
        logger.error("TTS failure: %s", e.detail)
        raise
    return ChatResponse(
        audio_url=audio_url,
        transcribed_text=user_text,
        llm_response=ai_reply,
        history=history[-20:],
    )

@app.post("/llm/query", response_model=ChatResponse)
async def llm_query(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Invalid audio file")
    text = transcribe_audio_bytes(audio_bytes)
    if not text:
        raise HTTPException(status_code=400, detail="Empty transcription")
    logger.info("LLM single-shot query chars=%d", len(text))
    ai_reply = llm_client.generate(text)
    logger.info("LLM single-shot reply chars=%d", len(ai_reply or ''))
    audio_url = tts_client.synthesize(ai_reply, "en-US-ken")
    return ChatResponse(audio_url=audio_url, transcribed_text=text, llm_response=ai_reply)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)