from fastapi import FastAPI, HTTPException, File, UploadFile, Request, WebSocket, WebSocketDisconnect
import uuid
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
import asyncio
from dotenv import load_dotenv
import assemblyai as aai
from starlette.websockets import WebSocketState
from datetime import datetime
from pathlib import Path

load_dotenv()

from services.stt_service import resilient_transcribe, transcribe_audio_bytes  
from services.streaming_transcriber import AssemblyAIStreamingTranscriber
from services.tts_service import MurfTTSClient 
from services.murf_ws_service import MurfWebSocketStreamer  
from services.llm_service import GeminiClient, build_chat_prompt 
from schemas.tts import ( 
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


# Real-time streaming transcription using AssemblyAI
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Get session_id from query params or generate one
    session_id = ws.query_params.get('session_id') if hasattr(ws, 'query_params') else None
    if not session_id:
        session_id = str(uuid.uuid4())
    await ws.accept()
    logger.info("✅ Ready for audio stream (AssemblyAI)")
    # Capture loop now so thread callbacks can schedule coroutines
    import asyncio
    loop = asyncio.get_running_loop()
    ws_closed = False
    last_partial_sent: str | None = None
    last_final_sent: str | None = None
    turn_finalized: bool = False

    # Send incremental (partial) transcript to client (as plain text frame) for live display
    async def send_transcript(transcript: str):
        if ws_closed or ws.client_state != WebSocketState.CONNECTED:
            return
        try:
            await ws.send_text(transcript)
        except Exception as e:
            logger.debug(f"(ignored) send partial after close: {e}")

    async def send_turn_end(transcript: str | None):
        if ws_closed or ws.client_state != WebSocketState.CONNECTED:
            return
        # Always include transcript so frontend renders exactly one bubble per utterance
        # Also include Gemini LLM response for UI
        user_text = transcript or last_partial_sent or last_final_sent or ""
        try:
            # Build prompt from history
            history = append_history(session_id, "user", user_text)
            prompt = build_chat_prompt(history)
            llm_response = llm_client.generate(prompt)
            # Sanitize and strictly limit Gemini response for Murf TTS reliability
            import re, uuid
            # Remove emojis and special symbols
            llm_response = re.sub(r'[^\x00-\x7F]+', '', llm_response)
            # Ensure proper punctuation
            if not llm_response.endswith(('.', '!', '?')):
                llm_response += '.'
            # Limit to 120 chars for short, reliable Murf answers
            if len(llm_response) > 120:
                sentences = re.split(r'(?<=[.!?])\s+', llm_response.strip())
                short_resp = ''
                for s in sentences:
                    if len(short_resp) + len(s) <= 120:
                        short_resp += (s + ' ')
                    else:
                        break
                llm_response = short_resp.strip()
            # Generate a unique context_id for this turn
            murf_context_id = f"turn_{uuid.uuid4().hex[:8]}"
            append_history(session_id, "assistant", llm_response)
            payload = {
                "type": "turn_end",
                "transcript": user_text,
                "llm_response": llm_response or "",
                "history": CHAT_HISTORY.get(session_id, [])[-20:]
            }
            await ws.send_json(payload)
            # Murf TTS streaming: send full response with context_id and end=True
            async def run_llm_stream():
                print(f"[LLM STREAM START] prompt: {prompt}")
                def do_stream():
                    murf_streamer = MurfWebSocketStreamer(MURF_API_KEY, voice_id="en-US-ken", context_id=murf_context_id)
                    logger.info('[Murf TTS] context_id=%s text=%s', murf_context_id, llm_response)
                    try:
                        murf_streamer.connect()
                        def push_audio_b64(b64: str):
                            if ws_closed or ws.client_state != WebSocketState.CONNECTED:
                                return
                            try:
                                asyncio.run_coroutine_threadsafe(ws.send_json({"type": "tts_chunk", "audio_b64": b64}), loop)
                            except Exception:
                                pass
                        def push_done():
                            if ws_closed or ws.client_state != WebSocketState.CONNECTED:
                                return
                            try:
                                asyncio.run_coroutine_threadsafe(ws.send_json({"type": "tts_done"}), loop)
                            except Exception:
                                pass
                        murf_streamer.send_text_chunk(llm_response, end=True)
                        murf_streamer.finalize(on_audio_chunk=push_audio_b64, on_done=push_done)
                    except Exception as e:
                        logger.error('Murf synth error: %s', e)
                await asyncio.get_running_loop().run_in_executor(None, do_stream)
                print("[LLM STREAM END]\n")
            asyncio.run_coroutine_threadsafe(run_llm_stream(), loop)
        except Exception as e:
            logger.error(f"LLM error: {e}")

    # Buffers + thread-safe wrappers used by AssemblyAI SDK thread
    transcript_buffer: list[str] = []
    def transcript_callback(transcript: str):  # partial
        nonlocal last_partial_sent, last_final_sent, turn_finalized
        if ws_closed or not transcript:
            return
        # Deduplicate identical partials
        if transcript == last_partial_sent:
            return
        last_partial_sent = transcript
        transcript_buffer.append(transcript)
        # Log partial transcript line (end_of_turn=False)
        logger.info('[Transcript] %s (end_of_turn=False)', transcript)
        # Stream partial to client
        if loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(send_transcript(transcript), loop)
            except RuntimeError:
                pass

    def turn_callback(transcript: str):  # final (end_of_turn)
        nonlocal last_final_sent, turn_finalized
        if ws_closed or not transcript:
            return
        if transcript == last_final_sent:
            return  # duplicate formatted final
        turn_finalized = True
        last_final_sent = transcript
        # Log final transcript line (end_of_turn=True)
        logger.info('[Transcript] %s (end_of_turn=True)', transcript)
        if loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(send_turn_end(transcript), loop)
            except RuntimeError:
                pass
    # Streaming now handled in send_turn_end for consistent LLM response

    # At process exit (dev convenience only)
    import atexit
    def print_final_transcript():
        if transcript_buffer:
            logger.info("Final statement: %s", transcript_buffer[-1])
    atexit.register(print_final_transcript)

    # Prepare audio file for saving
    uploads_dir = Path(__file__).parent / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    file_path = uploads_dir / f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pcm"
    total_bytes = 0
    transcriber = AssemblyAIStreamingTranscriber(
        sample_rate=16000,
        partial_callback=transcript_callback,
        final_callback=turn_callback
    )
    try:
        with open(file_path, "ab") as audio_file:
            while True:
                try:
                    data = await ws.receive_bytes()
                    if not data:
                        continue
                    audio_file.write(data)
                    total_bytes += len(data)
                    transcriber.stream_audio(data)
                except WebSocketDisconnect:
                    ws_closed = True
                    logger.info(f"🔴 Client disconnected, final size={total_bytes} bytes")
                    break
                except RuntimeError:
                    # Could be a text frame; attempt to handle gracefully
                    try:
                        txt = await ws.receive_text()
                        logger.warning(f"[ws] got unexpected text frame: {txt[:30]}")
                    except WebSocketDisconnect:
                        ws_closed = True
                        break
    finally:
        ws_closed = True
        try:
            transcriber.close()
        except Exception:
            pass
        logger.info(f"✅ Audio saved at {file_path} ({total_bytes} bytes)")
        logger.info("✅ Streaming session closed")



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

    