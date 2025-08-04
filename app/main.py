from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

app = FastAPI()

# Configuration
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"
MURF_API_KEY = os.getenv("MURF_API_KEY")
if not MURF_API_KEY:
    raise ValueError("MURF_API_KEY not found in .env file")

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
        response = requests.post(MURF_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        audio_url = response.json().get("audioFile", "")
        if not audio_url:
            raise HTTPException(status_code=500, detail="No audio file returned")
        return {"audio_url": audio_url}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)