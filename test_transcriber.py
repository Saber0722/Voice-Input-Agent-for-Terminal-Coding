"""
test_transcriber.py
-------------------
End-to-end test: speak → VAD captures → Whisper transcribes → prints text.
This is the first time both modules work together.
"""

from audio_capture import MicrophoneStream
from transcriber import Transcriber

transcriber = Transcriber(model_size="large-v3", device="cuda")
print("\nSpeak a sentence. Ctrl+C to stop.\n")

with MicrophoneStream() as mic:
    for utterance in mic.utterances():
        print("Transcribing...", end="\r")
        text = transcriber.transcribe(utterance)
        if text:
            print(f"You said: {text}")
        else:
            print("(nothing detected)   ")