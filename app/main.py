from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

app = FastAPI()

# Configuration
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"
MURF_API_KEY = os.getenv("MURF_API_KEY")
if not MURF_API_KEY:
    raise ValueError("MURF_API_KEY not found in .env file")

# Mount static files and templates
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Create uploads directory if it doesn't exist
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

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
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
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
        
        # Ensure uploads directory exists
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        
        # Create a unique filename
        file_extension = os.path.splitext(file.filename or "recording.ogg")[1] or ".ogg"
        unique_filename = f"recording_{os.urandom(4).hex()}{file_extension}"
        file_path = os.path.join(UPLOADS_DIR, unique_filename)
        
        print(f"Saving to: {file_path}")
        
        # Save the file
        file_content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        print(f"File saved successfully: {unique_filename}, size: {file_size} bytes")
        
        return {
            "filename": unique_filename,
            "content_type": file.content_type or "audio/ogg",
            "file_size": file_size
        }
    except Exception as e:
        print(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)