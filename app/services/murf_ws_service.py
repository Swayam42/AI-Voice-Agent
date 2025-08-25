import json, logging, websocket

PRIMARY_WS_URLS = [
    "wss://api.murf.ai/v1/speech/stream-input",
    "wss://api.murf.ai/v1/speech/stream-input/",  # trailing slash variant
    "wss://api.murf.ai/api/v1/speech/stream-input",
    "wss://murf.ai/api/v1/speech/stream-input",
]
logger = logging.getLogger("voice-agent.murf")

class MurfWebSocketStreamer:
    def __init__(self, api_key: str, voice_id: str = "en-US-ken", context_id: str = "voice_agent_ctx"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.context_id = context_id
        self.ws = None
        self.first_recv = True
        self.closed = False

    def connect(self):
        if self.ws: return
        last_err = None
        for base in PRIMARY_WS_URLS:
            url = f"{base}?api-key={self.api_key}&sample_rate=24000&channel_type=MONO&format=WAV"
            try:
                self.ws = websocket.create_connection(url, timeout=30)
                # Send voice config with context_id first (NO text here)
                voice_cfg = {
                    "voice_config": {
                        "voiceId": self.voice_id,
                        "style": "Conversational",
                        "rate": 0,
                        "pitch": 0,
                        "variation": 1
                    },
                    "context_id": self.context_id
                }
                self.ws.send(json.dumps(voice_cfg))
                logger.info("[MurfWS] Connected %s", base)
                return
            except Exception as e:
                last_err = e
                logger.warning("[MurfWS] Connect failed %s -> %s", base, e)
        raise RuntimeError(f"Unable to connect to Murf WebSocket (last error: {last_err})")

    def send_text_chunk(self, text: str, end=False):
        if not text.strip(): return
        self.connect()
        # Send text payload with context_id and end flag immediately after voice config
        msg = {
            "context_id": self.context_id,
            "text": text,
            "end": end
        }
        self.ws.send(json.dumps(msg))

    def finalize(self, on_audio_chunk=None, on_done=None):
        if not self.ws: return
        # Only finalize session, do NOT send text here
        try:
            while True:
                raw = self.ws.recv()
                if not raw: break
                data = json.loads(raw)
                if "audio" in data:
                    a = data["audio"]
                    if on_audio_chunk:
                        try:
                            on_audio_chunk(a)
                        except Exception:
                            pass
                    else:
                        print(f"[MURF AUDIO B64 CHUNK] {a[:100]}... len={len(a)}")
                if data.get("final"):
                    if on_done:
                        try:
                            on_done()
                        except Exception:
                            pass
                    break
        except Exception:
            pass
        self.close()

    def close(self):
        if self.closed: return
        self.closed = True
        try:
            self.ws and self.ws.close()
        except Exception:
            pass
