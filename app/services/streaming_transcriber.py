import os
import assemblyai as aai
from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions,
    StreamingParameters, StreamingSessionParameters,
    StreamingEvents, BeginEvent, TurnEvent,
    TerminationEvent, StreamingError
)
default_api_key = os.getenv("ASSEMBLYAI_API_KEY", "")
def on_begin(self, event: BeginEvent):
    print(f"Session started: {event.id}")
def make_on_turn(partial_callback=None, final_callback=None):
    def on_turn(self, event: TurnEvent):
        transcript = event.transcript
        if not transcript:
            return
        if event.end_of_turn:
            if getattr(event, 'turn_is_formatted', True) is False:
                try:
                    params = StreamingSessionParameters(format_turns=True)
                    self.set_params(params)
                except Exception:
                    pass
                return
            if final_callback:
                final_callback(transcript)
        else:
            if partial_callback:
                partial_callback(transcript)
    return on_turn

def on_termination(self, event: TerminationEvent):
    print(f"Session terminated after {event.audio_duration_seconds} s")

def on_error(self, error: StreamingError):
    print("Error:", error)

class AssemblyAIStreamingTranscriber:
    def __init__(self, sample_rate=16000, partial_callback=None, final_callback=None, api_key: str | None = None):
        key = api_key or default_api_key
        self.client = StreamingClient(
            StreamingClientOptions(
                api_key=key, api_host="streaming.assemblyai.com")
        )
        self.client.on(StreamingEvents.Begin, on_begin)
        self.client.on(StreamingEvents.Turn, make_on_turn(partial_callback, final_callback))
        self.client.on(StreamingEvents.Termination, on_termination)
        self.client.on(StreamingEvents.Error, on_error)
        self.client.connect(StreamingParameters(
            sample_rate=sample_rate, format_turns=True))
    def stream_audio(self, audio_chunk: bytes):
        self.client.stream(audio_chunk)
    def close(self):
        self.client.disconnect(terminate=True)
