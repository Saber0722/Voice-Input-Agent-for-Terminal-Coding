"""
wake_word.py
------------
Listens continuously for the wake word "Hey Jarvis" using openwakeword.
Runs on CPU — lightweight, leaves VRAM for Whisper and ollama.
"""

import numpy as np
import pyaudio
from openwakeword.model import Model


# ── Constants ──────────────────────────────────────────────────────────────────
SAMPLE_RATE     = 16000
CHUNK_SIZE      = 1280       # 80ms at 16kHz — openwakeword's expected frame size
WAKE_THRESHOLD  = 0.5
COOLDOWN_FRAMES = 60         # ~4.8s cooldown after trigger — prevents re-fires
WAKE_WORD_MODEL = "hey_jarvis"


class WakeWordDetector:
    def __init__(self, model_name: str = WAKE_WORD_MODEL, threshold: float = WAKE_THRESHOLD):
        self.threshold  = threshold
        self.model_name = model_name
        self._oww       = None
        self._pa        = None
        self._stream    = None

    def load(self):
        print(f"[wake word] Loading {self.model_name}...")
        self._oww = Model(
            wakeword_models=[self.model_name],
            inference_framework="onnx",
        )
        print(f"[wake word] Ready. Say 'Hey Jarvis' to activate.")

    def _open_stream(self):
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
           )

    def _close_stream(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()
        self._stream = None
        self._pa     = None

    def wait_for_wake_word(self) -> None:
        """Block until wake word is detected, then return."""
        self._open_stream()
        cooldown = 0

        try:
            while True:
                raw         = self._stream.read(CHUNK_SIZE, exception_on_overflow=False)
                audio_chunk = np.frombuffer(raw, dtype=np.int16)
                prediction  = self._oww.predict(audio_chunk)

                score = max(
                    v for k, v in prediction.items()
                    if self.model_name.split("_v")[0] in k
                )

                if cooldown > 0:
                    cooldown -= 1
                    continue

                if score >= self.threshold:
                    cooldown = COOLDOWN_FRAMES
                    self._close_stream()
                    return

        except Exception:
            self._close_stream()
            raise