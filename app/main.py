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
from services.llm_service import GeminiClient 
from services.web_search_service import TavilySearch
from services.weather_service import OpenWeather
from schemas.tts import ( 
    TextToSpeechRequest,
    TextToSpeechResponse,
    EchoResponse,
    ChatResponse,
    SimpleTranscriptionResponse,
    ChatTextRequest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("voice-agent")

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    logger.warning("ASSEMBLYAI_API_KEY not set; expect user to provide via Settings UI per session.")

gemini_key = os.getenv("GEMINI_API_KEY")
if not gemini_key:
    logger.warning("GEMINI_API_KEY not set; can be provided per session via Settings UI.")

MURF_API_KEY = os.getenv("MURF_API_KEY")
if not MURF_API_KEY:
    logger.warning("MURF_API_KEY not set; TTS will require a per-session key via Settings UI.")

app = FastAPI(title="AI Voice Agent", version="0.2.0")
# Default TTS client only if env key exists; per-session override supported at call-time
tts_client = MurfTTSClient(MURF_API_KEY) if MURF_API_KEY else None
llm_client = GeminiClient()
# Local knobs (not from env): tweak UI and TTS chunk lengths here
MAX_UI_ANSWER_CHARS: int =0  # 0 to disable UI trimming
MAX_TTS_CHARS: int = 240         # per-chunk size for Murf streaming

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

CHAT_HISTORY: dict[str, list] = {}
SESSION_SETTINGS: dict[str, dict] = {}

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

    # Look up any session-specific API keys
    settings = SESSION_SETTINGS.get(session_id) or {}
    aai_key = settings.get("ASSEMBLYAI_API_KEY") or aai.settings.api_key
    gemini_override = settings.get("GEMINI_API_KEY")
    tavily_override = settings.get("TAVILY_API_KEY")
    ow_override = settings.get("OPENWEATHER_API_KEY")
    murf_override = settings.get("MURF_API_KEY")

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
            # Append to history and let Gemini decide tool use (web search)
            history = append_history(session_id, "user", user_text)
            overrides = {k: v for k, v in {
                "GEMINI_API_KEY": gemini_override,
                "TAVILY_API_KEY": tavily_override,
                "OPENWEATHER_API_KEY": ow_override,
            }.items() if v}
            raw_reply = llm_client.chat(user_text, history, overrides=overrides)
            # Sanitize
            import re, uuid
            full_tts_text = re.sub(r'[^\x00-\x7F]+', '', raw_reply or '')
            full_tts_text = full_tts_text.strip()
            # Ensure proper punctuation for TTS
            if full_tts_text and not full_tts_text.endswith(('.', '!', '?')):
                full_tts_text += '.'
            # UI text may be trimmed, but TTS uses the full text
            ui_text = full_tts_text
            if MAX_UI_ANSWER_CHARS and MAX_UI_ANSWER_CHARS > 0 and len(ui_text) > MAX_UI_ANSWER_CHARS:
                sentences = re.split(r'(?<=[.!?])\s+', ui_text)
                short_resp = ''
                for s in sentences:
                    if len(short_resp) + len(s) <= MAX_UI_ANSWER_CHARS:
                        short_resp += (s + ' ')
                    else:
                        break
                ui_text = short_resp.strip()
            # Generate a unique context_id for this turn
            murf_context_id = f"turn_{uuid.uuid4().hex[:8]}"
            append_history(session_id, "assistant", ui_text)
            payload = {
                "type": "turn_end",
                "transcript": user_text,
                "llm_response": ui_text or "",
                "history": CHAT_HISTORY.get(session_id, [])[-20:]
            }
            await ws.send_json(payload)
            # Murf TTS streaming: send response in safe chunks (sentences) and end=True on last chunk
            async def run_llm_stream():
                print("[LLM STREAM START]")
                def do_stream():
                    # Use per-session Murf key if provided
                    murf_key = murf_override or MURF_API_KEY
                    if not murf_key:
                        logger.error('No Murf API key set for TTS streaming')
                        return
                    murf_streamer = MurfWebSocketStreamer(murf_key, voice_id="en-US-ken", context_id=murf_context_id)
                    logger.info('[Murf TTS] context_id=%s text_len=%d', murf_context_id, len(full_tts_text or ''))
                    try:
                        murf_streamer.connect()
                        # --- Split LLM text into Murf-safe chunks ---
                        def split_for_tts(text: str, max_chars: int) -> list[str]:
                            import re
                            chunks: list[str] = []
                            if not text:
                                return chunks
                            paras = [p.strip() for p in text.split('\n\n') if p and p.strip()]
                            for para in paras if paras else [text]:
                                # Split by sentence boundaries
                                parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if s.strip()]
                                buf = ''
                                for s in parts:
                                    # If a single sentence is too long, hard-wrap it
                                    if len(s) > max_chars:
                                        # wrap on spaces up to max_chars
                                        start = 0
                                        while start < len(s):
                                            end = min(start + max_chars, len(s))
                                            # try to break at last space in window
                                            window = s[start:end]
                                            brk = window.rfind(' ')
                                            if brk == -1 or start + brk < start + int(max_chars*0.6):
                                                brk = end - start
                                            piece = s[start:start+brk].strip()
                                            if piece:
                                                chunks.append(piece)
                                            start += brk
                                        continue
                                    # normal glue into buffer
                                    if not buf:
                                        buf = s
                                    elif len(buf) + 1 + len(s) <= max_chars:
                                        buf += ' ' + s
                                    else:
                                        chunks.append(buf)
                                        buf = s
                                if buf:
                                    chunks.append(buf)
                            return chunks

                        tts_chunks = split_for_tts(full_tts_text, MAX_TTS_CHARS)
                        if not tts_chunks:
                            tts_chunks = [full_tts_text]
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
                        # Send each chunk, end only on the last
                        for i, ch in enumerate(tts_chunks):
                            murf_streamer.send_text_chunk(ch, end=(i == len(tts_chunks)-1))
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
        final_callback=turn_callback,
        api_key=aai_key
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
                        msg = txt.strip().lower() if isinstance(txt, str) else ''
                        if msg == 'end_of_turn' or msg == '{"type":"end_of_turn"}':
                            # Force finalize using the latest transcript we have
                            forced_text = last_final_sent or last_partial_sent or ''
                            logger.info('[ws] received end_of_turn marker; finalizing with: %s', forced_text)
                            await send_turn_end(forced_text)
                        else:
                            logger.warning(f"[ws] got unexpected text frame: {txt[:40]}")
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
    if not tts_client:
        raise HTTPException(status_code=500, detail="TTS not configured. Set MURF_API_KEY in server or provide per-session in chat flow.")
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
    # sessionless here; could accept ?session_id to use overrides
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
    # Use session-specific AssemblyAI key if set
    s = (SESSION_SETTINGS.get(session_id) or {})
    aai_key = s.get("ASSEMBLYAI_API_KEY")
    user_text = transcribe_audio_bytes(audio_bytes, api_key=aai_key)
    if not user_text:
        raise HTTPException(status_code=400, detail="Empty transcription")
    history = append_history(session_id, "user", user_text)
    logger.info("LLM chat session=%s", session_id)
    overrides = {k: v for k, v in {
        "GEMINI_API_KEY": s.get("GEMINI_API_KEY"),
        "TAVILY_API_KEY": s.get("TAVILY_API_KEY"),
        "OPENWEATHER_API_KEY": s.get("OPENWEATHER_API_KEY"),
    }.items() if v}
    ai_reply = llm_client.chat(user_text, history, overrides=overrides)
    logger.info("LLM reply chars=%d session=%s", len(ai_reply or ''), session_id)
    append_history(session_id, "assistant", ai_reply)
    try:
        # Use per-session Murf key override if present
        murf_key = s.get("MURF_API_KEY") or MURF_API_KEY
        if not murf_key:
            raise HTTPException(status_code=500, detail="Murf TTS not configured")
        # Prefer ephemeral client to avoid mutating global
        local_client = MurfTTSClient(murf_key)
        audio_url = local_client.synthesize(ai_reply, "en-US-ken")
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
    ai_reply = llm_client.chat(text)
    logger.info("LLM single-shot reply chars=%d", len(ai_reply or ''))
    audio_url = tts_client.synthesize(ai_reply, "en-US-ken")
    return ChatResponse(audio_url=audio_url, transcribed_text=text, llm_response=ai_reply)

# --- Debug endpoints (optional): quick testing without audio ---
@app.get("/debug/web_search")
async def debug_web_search(query: str, max_results: int = 5):
    try:
        client = TavilySearch()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tavily unavailable: {e}")
    return client.search(query, max_results)

@app.get("/debug/weather")
async def debug_weather(location: str, units: str = "metric"):
    try:
        client = OpenWeather()
        return client.current_weather(location, units)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenWeather unavailable: {e}")

@app.get("/debug/llm_chat")
async def debug_llm_chat(q: str):
    try:
        reply = llm_client.chat(q)
        return {"query": q, "reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/debug/llm_chat_text")
async def debug_llm_chat_text(payload: ChatTextRequest):
    try:
        reply = llm_client.chat(payload.text)
        return {"query": payload.text, "reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Settings endpoints (kept above __main__ guard to ensure registration even when running this file directly)
@app.post("/settings/{session_id}")
async def set_session_settings(session_id: str, payload: dict):
    # Accept a JSON with any of: GEMINI_API_KEY, TAVILY_API_KEY, OPENWEATHER_API_KEY, ASSEMBLYAI_API_KEY, MURF_API_KEY
    allowed = {"GEMINI_API_KEY","TAVILY_API_KEY","OPENWEATHER_API_KEY","ASSEMBLYAI_API_KEY","MURF_API_KEY"}
    existing = SESSION_SETTINGS.setdefault(session_id, {})
    for k,v in (payload or {}).items():
        if k in allowed and isinstance(v, str) and v.strip():
            existing[k] = v.strip()
        elif k in allowed and (v is None or v == ""):
            existing.pop(k, None)
    return {"session_id": session_id, "settings": {k: ("set" if k in existing else None) for k in allowed}}

@app.get("/settings/{session_id}")
async def get_session_settings(session_id: str):
    s = SESSION_SETTINGS.get(session_id) or {}
    return {"session_id": session_id, "settings": {k: ("set" if k in s else None) for k in ["GEMINI_API_KEY","TAVILY_API_KEY","OPENWEATHER_API_KEY","ASSEMBLYAI_API_KEY","MURF_API_KEY"]}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

    