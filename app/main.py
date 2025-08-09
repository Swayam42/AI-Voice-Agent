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
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure API keys globally
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in .env file")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")
genai.configure(api_key=GEMINI_API_KEY)

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

class LLMQuery(BaseModel):
    query: str

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

@app.post("/llm/query")
async def llm_query(query_data: LLMQuery):
    try:
        print(f"Received LLM query: {query_data.query}")
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(query_data.query)
        print(f"LLM response: {response.text}")
        return {"response": response.text}
    except Exception as e:
        print(f"LLM query error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"LLM query failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)