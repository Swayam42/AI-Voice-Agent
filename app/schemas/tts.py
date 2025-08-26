from pydantic import BaseModel

class TextToSpeechRequest(BaseModel):
    text: str
    voiceId: str = "en-US-charles"

class TextToSpeechResponse(BaseModel):
    audio_url: str

class EchoResponse(BaseModel):
    audio_url: str
    transcription: str

class ChatResponse(BaseModel):
    audio_url: str
    transcribed_text: str
    llm_response: str | None = None
    history: list | None = None
    error: str | None = None

class SimpleTranscriptionResponse(BaseModel):
    transcription: str

class ChatTextRequest(BaseModel):
    text: str
