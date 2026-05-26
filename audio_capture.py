"""
audio_capture.py
----------------
Captures microphone input and uses WebRTC VAD to automatically detect
when the user starts and stops speaking. Returns a raw PCM audio chunk
(as bytes) for each complete utterance.

Key concepts:
- VAD (Voice Activity Detection): classifies each 30ms audio frame as
  speech or silence.
- Ring buffer: keeps the last ~300ms of audio always in memory so the
  beginning of a word is never lost.
- Padding: we wait for 900ms of silence before deciding the utterance ended.
"""

import os
import collections
import pyaudio
import webrtcvad
from contextlib import contextmanager


# ── Audio constants ────────────────────────────────────────────────────────────
SAMPLE_RATE          = 16000
FRAME_DURATION_MS    = 30
FRAME_BYTES          = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000) * 2
RING_BUFFER_FRAMES   = 10
SILENCE_FRAMES_TO_STOP = 30   # 900ms of silence = end of utterance
VAD_AGGRESSIVENESS   = 2


@contextmanager
def _suppress_stderr():
    """Redirect stderr to /dev/null at OS level to silence ALSA noise."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    os.dup2(devnull, 2)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)


class MicrophoneStream:
    """
    Opens the microphone and provides a generator that yields
    one complete audio utterance (as raw PCM bytes) per iteration.
    """

    def __init__(self, aggressiveness: int = VAD_AGGRESSIVENESS):
        self.vad = webrtcvad.Vad(aggressiveness)
        self._pa     = None
        self._stream = None

    def __enter__(self):
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=FRAME_BYTES // 2,
        )
        return self

    def __exit__(self, *_):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()

    def _read_frame(self) -> bytes:
        return self._stream.read(FRAME_BYTES // 2, exception_on_overflow=False)

    def utterances(self):
        """
        Generator. Blocks until a complete utterance is captured,
        then yields it as raw 16-bit mono PCM bytes.
        """
        ring         = collections.deque(maxlen=RING_BUFFER_FRAMES)
        voiced_frames = []
        silent_frame_count = 0
        speaking     = False

        while True:
            frame      = self._read_frame()
            is_speech  = self.vad.is_speech(frame, SAMPLE_RATE)

            if not speaking:
                ring.append(frame)
                if is_speech:
                    speaking      = True
                    voiced_frames = list(ring)
                    silent_frame_count = 0
            else:
                voiced_frames.append(frame)
                if is_speech:
                    silent_frame_count = 0
                else:
                    silent_frame_count += 1
                    if silent_frame_count >= SILENCE_FRAMES_TO_STOP:
                        yield b"".join(voiced_frames)
                        speaking           = False
                        voiced_frames      = []
                        silent_frame_count = 0
                        ring.clear()