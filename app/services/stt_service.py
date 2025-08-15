import time
import tempfile
import os
import assemblyai as aai
from fastapi import HTTPException

TRANSCRIBE_TIMEOUT = 30

def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_bytes)
    start_time = time.time()
    while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
        if time.time() - start_time > TRANSCRIBE_TIMEOUT:
            raise HTTPException(status_code=500, detail="Transcription timeout")
        transcript = transcriber.get_transcript(transcript.id)
        time.sleep(1)
    if transcript.status == aai.TranscriptStatus.error:
        raise HTTPException(status_code=500, detail="Transcription failed")
    return transcript.text.strip() if transcript.text else ""


def resilient_transcribe(audio_bytes: bytes) -> str:
    try:
        return transcribe_audio_bytes(audio_bytes)
    except Exception:
        # fallback to temp file path
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
            transcriber = aai.Transcriber(config=config)
            transcript = transcriber.transcribe(tmp_path)
            start_time = time.time()
            while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
                if time.time() - start_time > TRANSCRIBE_TIMEOUT:
                    raise HTTPException(status_code=500, detail="Transcription timeout")
                transcript = transcriber.get_transcript(transcript.id)
                time.sleep(1)
            if transcript.status == aai.TranscriptStatus.error:
                raise HTTPException(status_code=500, detail="Transcription failed")
            return transcript.text.strip() if transcript.text else ""
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
