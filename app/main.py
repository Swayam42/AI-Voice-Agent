from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env in the parent directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Murf API configuration
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"
MURF_API_KEY = os.getenv("MURF_API_KEY")
if not MURF_API_KEY:
    raise ValueError("MURF_API_KEY not found in .env file")

# Templates configuration (relative to app directory)
templates = Jinja2Templates(directory="templates")

class TextInput(BaseModel):
    text: str
    voiceId: str = "en-US-charles"  # Updated to new voice
    languageCode: str = "en-US"     # Default language
    style: str = "Conversational"   # Updated to new style
    multiNativeLocale: str = "hi-IN"  # Added multiNativeLocale

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate_audio")
async def generate_audio(input: TextInput):
    if not input.text:
        raise HTTPException(status_code=400, detail="No text provided in 'text' field")

    headers = {
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": input.text,
        "voiceId": input.voiceId,
        "style": input.style,
        "languageCode": input.languageCode,
        "multiNativeLocale": input.multiNativeLocale  # Added to payload
    }

    try:
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
        response.raise_for_status()

        response_data = response.json()
        audio_url = response_data.get("audioFile", "")
        if not audio_url:
            raise HTTPException(status_code=500, detail={"error": "No audio file returned", "murf_response": response_data})

        return {"audio_url": audio_url, "murf_response": response_data}

    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail={"error": f"Murf API HTTP error: {e.response.status_code}", "details": e.response.text, "request_payload": payload})
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail={"error": "Failed to connect to Murf API", "details": str(e), "request_payload": payload})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)