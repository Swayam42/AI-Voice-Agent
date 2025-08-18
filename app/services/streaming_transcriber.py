import os
import assemblyai as aai
from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions,
    StreamingParameters, StreamingSessionParameters,
    StreamingEvents, BeginEvent, TurnEvent,
    TerminationEvent, StreamingError
)

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY", "")


def on_begin(self, event: BeginEvent):
    print(f"Session started: {event.id}")



def make_on_turn(transcript_callback):
    def on_turn(self, event: TurnEvent):
        transcript = event.transcript
        if transcript:
            transcript_callback(transcript)
        if event.end_of_turn and not event.turn_is_formatted:
            params = StreamingSessionParameters(format_turns=True)
            self.set_params(params)
    return on_turn


def on_termination(self, event: TerminationEvent):
    print(f"Session terminated after {event.audio_duration_seconds} s")


def on_error(self, error: StreamingError):
    print("Error:", error)


class AssemblyAIStreamingTranscriber:
    def __init__(self, sample_rate=16000, transcript_callback=None):
        self.client = StreamingClient(
            StreamingClientOptions(
                api_key=aai.settings.api_key, api_host="streaming.assemblyai.com")
        )
        self.client.on(StreamingEvents.Begin, on_begin)
        if transcript_callback:
            self.client.on(StreamingEvents.Turn, make_on_turn(transcript_callback))
        else:
            self.client.on(StreamingEvents.Turn, lambda self, event: None)
        self.client.on(StreamingEvents.Termination, on_termination)
        self.client.on(StreamingEvents.Error, on_error)

        self.client.connect(StreamingParameters(
            sample_rate=sample_rate, format_turns=False))

    def stream_audio(self, audio_chunk: bytes):
        self.client.stream(audio_chunk)

    def close(self):
        self.client.disconnect(terminate=True)
