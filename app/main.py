from fastapi import FastAPI, HTTPException, File, UploadFile, Request
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
import google.generativeai as genai

load_dotenv()

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in .env file")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
if not os.getenv("GEMINI_API_KEY"):
    raise ValueError("GEMINI_API_KEY not found in .env file")

app = FastAPI()
MURF_API_KEY = os.getenv("MURF_API_KEY")  
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

class TextInput(BaseModel):
    text: str
    voiceId: str = "en-US-charles"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        return HTMLResponse(f"Error loading page: {str(e)}", status_code=500)

@app.post("/generate_audio")
async def generate_audio(input: TextInput):
    try:
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        response = requests.post(MURF_API_URL, headers=headers, json=input.dict())
        response.raise_for_status()
        audio_url = response.json().get("audioFile")
        if not audio_url:
            raise HTTPException(status_code=500, detail="No audio file")
        return {"audio_url": audio_url}
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="TTS service failed")
    except Exception:
        raise HTTPException(status_code=500, detail="TTS error")

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        file_content = await file.read()
        return {"filename": file.filename, "content_type": file.content_type, "size": len(file_content)}
    except Exception:
        raise HTTPException(status_code=500, detail="Upload failed")

@app.post("/transcribe/file")
async def transcribe_file(file: UploadFile = File(...)):
    try:
        audio_data = await file.read()
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_data)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > 30:
                raise HTTPException(status_code=500, detail="Transcription timeout")
            transcript = transcriber.get_transcript(transcript.id)
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.error:
            raise HTTPException(status_code=500, detail="Transcription failed")
        return {"transcription": transcript.text.strip() if transcript.text else ""}
    except Exception:
        raise HTTPException(status_code=500, detail="STT error")
    
@app.post("/tts/echo")
async def tts_echo(file: UploadFile = File(...)):
    try:
        audio_data = await file.read()
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_data)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > 30:
                raise HTTPException(status_code=500, detail="Transcription timeout")
            transcript = transcriber.get_transcript(transcript.id)
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.error:
            raise HTTPException(status_code=500, detail="Transcription failed")
        text = transcript.text.strip() if transcript.text else ""
        if not text:
            raise HTTPException(status_code=400, detail="Empty transcription")
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        payload = {"text": text, "voiceId": "en-US-charles"}
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        audio_url = response.json().get("audioFile")
        if not audio_url:
            raise HTTPException(status_code=500, detail="No audio file")
        return {"audio_url": audio_url, "transcription": text}
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="TTS service failed")
    except Exception:
        raise HTTPException(status_code=500, detail="TTS error")

def getResponsefromGemini(prompt: str) -> str:
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        return model.generate_content(prompt).text.strip()
    except Exception:
        return "Sorry, I couldn't process that."

CHAT_HISTORY = {}

def build_chat_prompt(history: list) -> str:
    lines = ["You are a helpful, concise voice AI. Keep replies brief."]
    lines.extend([f"{('User' if msg['role'] == 'user' else 'Assistant')}: {msg['content']}" for msg in history[-10:]])
    lines.append("Assistant:")
    return "\n".join(lines)

def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    try:
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_bytes)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > 30:
                raise Exception("Transcription timeout")
            transcript = transcriber.get_transcript(transcript.id)
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.error:
            raise Exception("Transcription failed")
        return transcript.text.strip() if transcript.text else ""
    except Exception:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            transcript = transcriber.transcribe(tmp_path)
            start_time = time.time()
            while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
                if time.time() - start_time > 30:
                    raise Exception("Transcription timeout")
                transcript = transcriber.get_transcript(transcript.id)
                time.sleep(1)
            return transcript.text.strip() if transcript.text and transcript.status == aai.TranscriptStatus.completed else ""
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        if not audio_bytes or len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="Invalid audio file")
        user_text = transcribe_audio_bytes(audio_bytes)
        if not user_text:
            raise HTTPException(status_code=400, detail="Empty transcription")
        history = CHAT_HISTORY.setdefault(session_id, [])
        history.append({"role": "user", "content": user_text})
        prompt = build_chat_prompt(history)
        ai_reply = getResponsefromGemini(prompt)
        history.append({"role": "assistant", "content": ai_reply})
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        payload = {"text": ai_reply, "voiceId": "en-US-ken"}
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        audio_url = response.json().get("audioFile")
        if not audio_url:
            raise HTTPException(status_code=500, detail="TTS failed")
        return {"audio_url": audio_url, "transcribed_text": user_text, "llm_response": ai_reply, "history": history[-20:]}
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="TTS service failed")
    except HTTPException:
        raise
    except Exception:
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        payload = {"text": "I'm having trouble connecting right now", "voiceId": "en-US-ken"}
        fallback_response = requests.post(MURF_API_URL, headers=headers, json=payload)
        fallback_response.raise_for_status()
        return {"audio_url": fallback_response.json().get("audioFile"), "error": "Service unavailable"}

@app.post("/llm/query")
async def llm_query(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        if not audio_bytes or len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="Invalid audio file")
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_bytes)
        start_time = time.time()
        while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
            if time.time() - start_time > 30:
                raise HTTPException(status_code=500, detail="Transcription timeout")
            transcript = transcriber.get_transcript(transcript.id)
            time.sleep(1)
        if transcript.status == aai.TranscriptStatus.error:
            raise HTTPException(status_code=500, detail="Transcription failed")
        text = transcript.text.strip() if transcript.text else ""
        if not text:
            raise HTTPException(status_code=400, detail="Empty transcription")
        ai_reply = getResponsefromGemini(text)
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        payload = {"text": ai_reply, "voiceId": "en-US-ken"}
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        audio_url = response.json().get("audioFile")
        if not audio_url:
            raise HTTPException(status_code=500, detail="TTS failed")
        return {"audio_url": audio_url, "transcribed_text": text, "llm_response": ai_reply}
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="TTS service failed")
    except Exception:
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        payload = {"text": "I'm having trouble connecting right now", "voiceId": "en-US-ken"}
        fallback_response = requests.post(MURF_API_URL, headers=headers, json=payload)
        fallback_response.raise_for_status()
        return {"audio_url": fallback_response.json().get("audioFile"), "error": "Service unavailable"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)