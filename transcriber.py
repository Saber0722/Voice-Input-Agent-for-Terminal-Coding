"""
transcriber.py
--------------
Wraps faster-whisper to transcribe raw PCM audio bytes into text.

The model is loaded once on initialization (expensive ~2s) and then
reused for every transcription call (~0.3s on RTX 4060 with small model).

Model size trade-offs:
  tiny   — ~150MB VRAM, ~0.1s,  good enough for clear speech
  base   — ~300MB VRAM, ~0.2s,  better accuracy
  small  — ~500MB VRAM, ~0.3s,  recommended sweet spot
  medium — ~1.5GB VRAM, ~0.6s,  best accuracy, still fast on 4060
  large  — ~3GB VRAM,   ~1.2s,  overkill for this use case

We default to "small" — great accuracy, barely uses your 8GB VRAM.
"""

import numpy as np
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "cuda"):
        print(f"Loading Whisper {model_size} on {device}...")
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="float16",  # float16 on GPU = faster + less VRAM than float32
        )
        print("Whisper ready.")

    def transcribe(self, pcm_bytes: bytes) -> str:
        """
        Convert raw 16-bit mono PCM bytes → transcribed string.

        Steps:
          1. PCM bytes are int16 values — numpy reads them as such
          2. Divide by 32768.0 to normalize into [-1.0, 1.0] float32
             (32768 = 2^15 = max value of a signed 16-bit integer)
          3. Pass to faster-whisper which returns segment objects
          4. Join all segment texts into one string
        """
        # Step 1 & 2: bytes → normalized float32 array
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # Step 3: transcribe
        # beam_size=5 is the default — higher = more accurate but slower
        # language="en" skips language detection (saves ~0.1s), remove if multilingual
        # vad_filter=True tells Whisper to also do its own internal VAD pass
        # this double-VAD approach catches any silence we might have leaked through
        segments, _info = self.model.transcribe(
            audio,
            beam_size=5,
            language="en",
            vad_filter=True,
        )

        # Step 4: segments is a generator — consume it and join text
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip()