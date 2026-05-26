"""
test_audio.py
-------------
Run this standalone to verify your mic and VAD are working correctly.
Speak into your mic — it should print "Captured utterance: XXXX bytes"
each time you finish a sentence. Ctrl+C to exit.
"""

from audio_capture import MicrophoneStream

print("VAD test — speak into your mic. Ctrl+C to stop.\n")

with MicrophoneStream() as mic:
    for i, utterance in enumerate(mic.utterances(), 1):
        duration_ms = len(utterance) / 2 / 16000 * 1000  # bytes → ms
        print(f"[{i}] Captured utterance: {len(utterance)} bytes  ({duration_ms:.0f} ms)")