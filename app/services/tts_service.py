import requests
from fastapi import HTTPException

class MurfTTSClient:
    def __init__(self, api_key: str, base_url: str = "https://api.murf.ai/v1/speech/generate"):
        self.api_key = api_key
        self.base_url = base_url

    def synthesize(self, text: str, voice_id: str) -> str:
        headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        payload = {"text": text, "voiceId": voice_id}
        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=40)
            resp.raise_for_status()
            audio_url = resp.json().get("audioFile")
            if not audio_url:
                raise HTTPException(status_code=500, detail="No audio file")
            return audio_url
        except requests.exceptions.RequestException:
            raise HTTPException(status_code=500, detail="TTS service failed")

