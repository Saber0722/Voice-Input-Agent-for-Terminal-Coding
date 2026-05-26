# REPORT — voice-aider

## Motivation and target agent choice

The assignment asked for a voice front-end that eliminates as much keyboard and mouse interaction as possible. The first decision was which terminal agent to wrap.

I considered three options: [Claude Code](https://claude.ai/code), [opencode](https://opencode.ai), and [Aider](https://aider.chat). Claude Code and opencode are newer and have richer TUI surfaces, but that richness is exactly what makes them harder to drive programmatically — their interfaces are designed for human eyes navigating menus, not for a process injecting lines of text. Aider operates through a simple read-eval-print loop: it prints a prompt, waits for a line of text, and streams a response. That contract is ideal for voice integration, because the integration layer only needs to do one thing reliably: deliver a line of text at the right moment. Aider also supports any model reachable through its backend, so I could run everything locally with Ollama and avoid API latency.

---
## Architecture overview

The pipeline is a straight line:

```
Microphone → WebRTC VAD → faster-whisper → Aider PTY
```

A background thread continuously reads from the microphone in 30 ms frames. WebRTC VAD classifies each frame as speech or silence. When a run of speech frames ends (configurable silence budget), the accumulated audio is handed off to the transcription thread, which runs faster-whisper and puts the result on a queue. The main thread pulls from the queue and writes the text into Aider's PTY as if a human had typed it and pressed Enter.

An optional wake-word layer (openwakeword, "Hey Jarvis") sits in front of VAD so that ambient conversation is not accidentally sent to the agent. It can be toggled off in `config.yaml` for a demo where continuous listening is preferable.

---
## Key design decisions

### Speech-to-text engine: faster-whisper

I evaluated three options:

- **Google Speech-to-Text / Deepgram** — high accuracy, low latency over a good connection, but require sending audio to an external service. Unacceptable for a coding assistant where the user may be discussing proprietary code.
- **Vosk** — fully local, very fast, small models. Accuracy on technical vocabulary (function names, library names, programming jargon) is noticeably worse than Whisper.
- **faster-whisper** — a CTranslate2-optimised reimplementation of OpenAI Whisper. Runs entirely locally, GPU-accelerated on CUDA, and handles technical vocabulary well because Whisper was trained on a broad corpus that includes code-adjacent text. The `medium` model fits comfortably in 2–3 GB of VRAM, leaving the rest free for the LLM.

faster-whisper was the clear choice: local, accurate on jargon, and fast enough that the transcription latency (< 1 s on an RTX 4060 for a typical utterance) does not feel disruptive.

---

### Voice activity detection: webrtcvad

Push-to-talk would require keyboard interaction, defeating the purpose. I needed automatic endpoint detection. The main alternatives were:

- **Silence by amplitude threshold** — simple but unreliable in noisy environments; a quieter speaker would trigger false endpoints mid-sentence.
- **Silero VAD** — neural, more robust, but adds a PyTorch dependency and runs inference per frame, increasing latency.
- **webrtcvad** — Google's WebRTC voice activity detector, compiled as a small C extension. It uses a combination of energy, zero-crossing rate, and spectral features to classify 10/20/30 ms frames. It is not as robust as a neural VAD on extreme noise, but it is deterministic, extremely fast (microseconds per frame), and has no GPU requirement. For a developer's workspace — reasonably controlled audio environment — it is more than adequate.

The aggressiveness level and the silence-frame budget (how many consecutive silent frames constitute an endpoint) are exposed in `config.yaml` so they can be tuned per environment without touching code.

---

### Aider integration: PTY via pexpect

This was the trickiest decision. There are three ways to talk to a CLI tool programmatically:

1. **subprocess with stdin/stdout pipes** — simple, but many CLI tools detect that stdout is not a TTY and change their behaviour: they disable colour, buffer output aggressively, or suppress the prompt entirely. Aider falls into this category; driving it over plain pipes required polling heuristics to detect when a response was complete.
2. **PTY (pseudo-terminal) via pexpect** — the process sees a real terminal. Prompts appear, colour codes are emitted, and readline is active. The integration layer can `expect()` for the prompt string to know precisely when Aider is ready for the next input. This is the approach used in the final implementation.
3. **Aider's Python API** — Aider does expose some programmatic interfaces, but they are not stable across versions and require importing Aider as a library rather than running it as a subprocess, which would tightly couple the version of Aider to the voice layer.

PTY with pexpect gives clean prompt detection, correct output rendering, and decouples the voice layer from Aider's internals entirely.


---
### Wake word: openwakeword

openwakeword provides pretrained TensorFlow Lite models for common wake phrases and runs at low CPU cost alongside the VAD loop. "Hey Jarvis" was chosen because it is reliably distinct from typical developer speech and the pretrained model performs well without fine-tuning. The wake-word stage is optional; in a demo context where ambient speech is not a concern, it can be disabled to allow truly continuous listening.


---

## Trade-offs and limitations

**Latency.** There is an unavoidable gap between the end of speech and Aider receiving the text: VAD silence budget (~0.5–1 s) + Whisper inference (~0.5–1 s). Total round-trip before Aider starts responding is roughly 1–2 seconds. This is acceptable for the deliberate, longer utterances typical of coding requests, but would feel sluggish for very short commands.

**Accuracy on highly technical terms.** Whisper handles most programming vocabulary well, but unusual library names, variable names, or acronyms are occasionally mis-transcribed. Users learn quickly to either spell out ambiguous terms or correct via a follow-up voice utterance. A post-processing step with a custom vocabulary or a phoneme-level correction layer could address this but was not implemented.

**Single-microphone noise robustness.** webrtcvad is designed for clean to moderately noisy environments. Significant background noise (open-plan office, music) will degrade VAD accuracy and may cause Whisper to receive truncated utterances. A beamforming microphone or a neural VAD (Silero) would improve robustness at the cost of additional complexity.

**No audio output.** Per the specification, responses are displayed on screen only. Text-to-speech output would complete the hands-free loop — the user would never need to glance at the screen to know when Aider had finished — but was explicitly out of scope.

**Platform.** Development and testing were done on Arch Linux with an NVIDIA GPU. The webrtcvad patch and cuBLAS symlink workarounds are Arch-specific. The core pipeline is portable, but the setup instructions would differ on other distributions or on macOS/Windows.

**Session state.** If Aider crashes or is restarted, the conversation context is lost. The "new session" voice command provides a controlled reset, but there is no automatic recovery from unexpected termination.

---

## What I would do differently with more time

- Replace webrtcvad with Silero VAD for better noise robustness without sacrificing the local-only constraint.
- Add a thin correction layer that applies a developer-vocabulary dictionary to Whisper's output before sending to Aider, reducing mis-transcriptions of common library and function names.
- Implement text-to-speech as an opt-in mode so users can work with the screen minimised.
- Package as a proper CLI tool (`pipx install voice-aider`) with a `--agent` flag that selects between Aider, Claude Code, and opencode backends.
- Add a visual overlay (small floating terminal widget) showing the last recognised utterance and transcription confidence, giving the user immediate feedback on what was heard before Aider processes it.