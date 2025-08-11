from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv
import assemblyai as aai
import time
import tempfile
import shutil
import google.generativeai as genai
from typing import List, Dict

# Load environment variables
load_dotenv()

# Configure API keys globally
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in .env file")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
if not os.getenv("GEMINI_API_KEY"):
    raise ValueError("GEMINI_API_KEY not found in .env file")

app = FastAPI()

# Configuration
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"
MURF_API_KEY = os.getenv("MURF_API_KEY")
if not MURF_API_KEY:
    raise ValueError("MURF_API_KEY not found in .env file")

# Mount static files and templates
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

class TextInput(BaseModel):
    text: str
    voiceId: str = "en-US-charles"
    languageCode: str = "en-US"
    style: str = "Conversational"
    multiNativeLocale: str = "hi-IN"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        print("Request received for home page")
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        print(f"Error rendering index.html: {str(e)}")
        return HTMLResponse(f"Error rendering page: {str(e)}", status_code=500)

@app.post("/generate_audio")
async def generate_audio(input: TextInput):
    headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
    payload = input.dict()
    try:
        print(f"Generating audio with payload: {payload}")
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
        print(f"Murf response status: {response.status_code}, text: {response.text}")
        response.raise_for_status()
        audio_url = response.json().get("audioFile", "")
        if not audio_url:
            raise HTTPException(status_code=500, detail="No audio file returned")
        return {"audio_url": audio_url}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        print(f"Received file: {file.filename}, type: {file.content_type}")
        file_content = await file.read()
        file_size = len(file_content)
        print(f"File received successfully: {file.filename}, size: {file_size} bytes")
        return {
            "filename": file.filename,
            "content_type": file.content_type or "audio/ogg",
            "file_size": file_size
        }
    except Exception as e:
        print(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/transcribe/file")
async def transcribe_file(file: UploadFile = File(...)):
    try:
        audio_data = await file.read()
        print(f"Received audio data for transcription, size: {len(audio_data)} bytes")
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_data)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > 30:
                raise HTTPException(status_code=500, detail="Transcription timeout")
            transcript = transcriber.get_transcript(transcript.id)
            print(f"Transcription status: {transcript.status}")
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.error:
            error_detail = transcript.error or "Unknown error"
            raise HTTPException(status_code=500, detail=f"Transcription failed: {error_detail}")
        if transcript.status != aai.TranscriptStatus.completed:
            raise HTTPException(status_code=500, detail="Transcription did not complete")
        transcription_text = transcript.text
        return {"transcription": transcription_text}
    except Exception as e:
        print(f"Transcription error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")

@app.post("/tts/echo")
async def tts_echo(file: UploadFile = File(...)):
    try:
        audio_data = await file.read()
        print(f"Received audio data, size: {len(audio_data)} bytes")
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_data)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > 30:
                raise HTTPException(status_code=500, detail="Transcription timeout")
            transcript = transcriber.get_transcript(transcript.id)
            print(f"Transcription status: {transcript.status}")
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.error:
            print(f"Transcription error: {transcript.error}")
            raise HTTPException(status_code=500, detail=transcript.error or "Transcription failed")
        if transcript.status != aai.TranscriptStatus.completed:
            raise HTTPException(status_code=500, detail="Transcription did not complete")
        text = transcript.text or ""
        print(f"Transcribed text: '{text}'")
        if not text.strip():
            raise HTTPException(status_code=400, detail="Empty transcription")
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "voiceId": "en-US-charles",
            "style": "Conversational",
            "multiNativeLocale": "hi-IN"
        }
        print(f"Murf payload: {payload}")
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
        print(f"Murf response status: {response.status_code}, text: {response.text}")
        response.raise_for_status()
        audio_url = response.json().get("audioFile", "")
        if not audio_url:
            raise HTTPException(status_code=500, detail="No audio file returned")
        return {"audio_url": audio_url, "transcription": text}
    except requests.exceptions.RequestException as e:
        print(f"Murf API error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Helper function for Gemini API
def getResponsefromGemini(prompt: str) -> str:
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini error: {e}")
        return "Sorry, I couldn't process that."

# ---------------- Chat History (In-Memory) ----------------
# Structure: { session_id: [ {"role": "user"|"assistant", "content": str}, ... ] }
CHAT_HISTORY: Dict[str, List[Dict[str, str]]] = {}

def build_chat_prompt(history: List[Dict[str, str]]) -> str:
    """Convert history into a single prompt for Gemini."""
    lines = ["You are a helpful, concise voice AI. Keep replies brief unless asked to elaborate."]
    for msg in history[-10:]:  # limit to last 10 messages to control token size
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    lines.append("Assistant:")
    return "\n".join(lines)

def transcribe_audio_bytes(audio_bytes: bytes, timeout: int = 40) -> str:
    """Attempt transcription directly; if empty, retry via temp file path."""
    config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
    transcriber = aai.Transcriber(config=config)
    # First attempt: direct
    try:
        transcript = transcriber.transcribe(audio_bytes)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > timeout:
                raise RuntimeError("Transcription timeout (direct bytes)")
            transcript = transcriber.get_transcript(transcript.id)
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.completed and transcript.text and transcript.text.strip():
            return transcript.text.strip()
    except Exception as e:
        print(f"Direct transcription attempt failed: {e}")

    # Fallback attempt: write to temp file
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        transcript = transcriber.transcribe(tmp_path)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > timeout:
                raise RuntimeError("Transcription timeout (temp file)")
            transcript = transcriber.get_transcript(transcript.id)
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.error:
            raise RuntimeError(transcript.error or "Transcription failed")
        return (transcript.text or "").strip()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    """Conversational endpoint with chat history.
    Flow: audio -> STT -> append user msg -> LLM w/ history -> append assistant -> TTS -> return."""
    try:
        audio_bytes = await file.read()
        if not audio_bytes or len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="Uploaded file is empty or too small.")

        # Transcribe (with fallback)
        user_text = transcribe_audio_bytes(audio_bytes)
        print(f"Transcribed (user) text: '{user_text}' (len={len(user_text)})")
        if not user_text:
            raise HTTPException(status_code=400, detail="Empty transcription")

        # Update history
        history = CHAT_HISTORY.setdefault(session_id, [])
        history.append({"role": "user", "content": user_text})

        # Build prompt & LLM response
        prompt = build_chat_prompt(history)
        ai_reply = getResponsefromGemini(prompt)
        history.append({"role": "assistant", "content": ai_reply})

        # TTS via Murf
        murf_headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        murf_payload = {"text": ai_reply, "voiceId": "en-US-ken"}
        murf_response = requests.post(MURF_API_URL, headers=murf_headers, json=murf_payload)
        murf_response.raise_for_status()
        audio_url = murf_response.json().get("audioFile")
        if not audio_url:
            raise HTTPException(status_code=500, detail="No audio file returned from Murf")

        return {
            "audio_url": audio_url,
            "transcribed_text": user_text,
            "llm_response": ai_reply,
            "history": history[-20:],  # recent history
            "debug": {"transcribed_length": len(user_text)}
        }
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"agent_chat unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/llm/query")
async def llm_query(file: UploadFile = File(...)):
    try:
        if not file:
            print("No file uploaded in request!")
            raise HTTPException(status_code=400, detail="No file uploaded. Make sure the field name is 'file'.")
        audio_bytes = await file.read()
        print(f"Received audio data, size: {len(audio_bytes)} bytes, content_type: {file.content_type}")
        if not audio_bytes or len(audio_bytes) < 100:
            print("Uploaded file is empty or too small!")
            raise HTTPException(status_code=400, detail="Uploaded file is empty or too small.")

        # ...existing code...
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_bytes)

        # Wait for transcription to complete
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > 30:
                raise HTTPException(status_code=500, detail="Transcription timeout")
            transcript = transcriber.get_transcript(transcript.id)
            print(f"Transcription status: {transcript.status}")
            time.sleep(1)

        if transcript.status == aai.TranscriptStatus.error:
            raise HTTPException(status_code=500, detail=f"AssemblyAI error: {transcript.error or 'Unknown error'}")

        text = transcript.text
        print(f"Transcribed text: '{text}'")

        # Get response from Gemini
        ai_reply = getResponsefromGemini(text)
        print(f"Gemini response: '{ai_reply}'")

        # Send to Murf API
        murf_headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        murf_payload = {
            "text": ai_reply,
            "voiceId": "en-US-ken"
        }
        murf_response = requests.post(MURF_API_URL, headers=murf_headers, json=murf_payload)
        murf_response.raise_for_status()
        print(f"Murf response: {murf_response.json()}")

        audio_url = murf_response.json().get("audioFile")
        if not audio_url:
            raise HTTPException(status_code=500, detail="No audio file returned from Murf")

        # Return transcribed text and LLM response as well
        return {
            "audio_url": audio_url,
            "transcribed_text": text,
            "llm_response": ai_reply
        }

    except requests.exceptions.RequestException as e:
        print(f"Murf API error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)