# voice-aider

A voice input interface for [Aider](https://aider.chat), a terminal-based AI coding agent.
Speak your coding requests — Aider responds on screen. No keyboard required after startup.

---

## How it works

```
Microphone → VAD → Whisper STT → Aider (via PTY)
```

- **WebRTC VAD** detects speech endpoints automatically — no push-to-talk needed
- **faster-whisper** (local, GPU-accelerated) transcribes speech to text
- **pexpect PTY** injects transcribed text into Aider as if typed at the keyboard
- Aider's responses stream to the terminal in real time

---

## Requirements

- Python 3.11+
- NVIDIA GPU (tested on RTX 4060 8 GB)
- CUDA 12.x with cuBLAS
- [Ollama](https://ollama.com) running locally with `qwen2.5-coder:7b` pulled
- PortAudio — `sudo pacman -S portaudio` (Arch) / `sudo apt install portaudio19-dev` (Debian/Ubuntu)
- ffmpeg — `sudo pacman -S ffmpeg` / `sudo apt install ffmpeg`

---

## Setup

### 1. Clone and create environment

```bash
git clone <repo-url>
cd voice-aider
uv venv
source .venv/bin/activate
uv sync
```

### 2. Fix webrtcvad for Python 3.11+

`webrtcvad` uses `pkg_resources` which is not bundled in Python 3.11+. Patch it with:

```bash
sed -i 's/__version__ = pkg_resources.get_distribution.*/__version__ = "2.0.10"/' \
    .venv/lib/python3.11/site-packages/webrtcvad.py
```

### 3. Fix CUDA cuBLAS symlinks (Arch Linux only)

```bash
sudo ln -s /opt/cuda/lib64/libcublas.so.13    /opt/cuda/lib64/libcublas.so.12
sudo ln -s /opt/cuda/lib64/libcublasLt.so.13  /opt/cuda/lib64/libcublasLt.so.12
echo 'export LD_LIBRARY_PATH=/opt/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### 4. Pull the model

```bash
ollama pull qwen2.5-coder:7b
```

### 5. Run

```bash
uv run python voice_agent.py
```

Aider starts automatically. Once you see the `>` prompt in the terminal, start speaking.

---

## Voice commands

| Say | Action |
|-----|--------|
| "exit" / "quit" / "goodbye" | Shut down voice-aider |
| "new session" / "start over" | Restart Aider with a fresh context |

Everything else is forwarded to Aider as a coding request.


---

## Configuration

Edit the constants at the top of `voice_agent.py`:

| Variable | Default | Description |
|---|---|---|
| `WHISPER_MODEL` | `medium` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `WHISPER_DEVICE` | `cuda` | `cuda` or `cpu` |
| `AIDER_MODEL` | `ollama/qwen2.5-coder:7b` | Any model string supported by Aider |

Additional VAD and voice-command settings are in `config.yaml`.

---

## Demo setup time

**~2 minutes** from a cold start:

| Step | Time |
|---|---|
| Ollama model warm-up | ~20 s |
| Whisper `medium` model load | ~10 s |
| Aider startup | ~5 s |

If the Whisper model is already cached (`~/.cache/huggingface/`) and Ollama is already running, total setup is under 60 seconds.

---

## Project structure

```
voice-aider/
├── voice_agent.py       # Entry point — main loop, threading, command resolution
├── audio_capture.py     # Microphone input and WebRTC VAD-based segmentation
├── transcriber.py       # faster-whisper STT wrapper
├── agent_interface.py   # PTY/subprocess wrapper around Aider
├── wake_word.py         # openwakeword detector ("Hey Jarvis")
├── config.yaml          # Tunable VAD, model, and voice-command settings
├── test_audio.py        # Mic + VAD integration test
├── test_transcriber.py  # End-to-end mic → Whisper test
├── test_agent.py        # Aider PTY interface test
└── pyproject.toml
```

---
## Running the tests

```bash
# Microphone and VAD
uv run python test_audio.py

# End-to-end transcription
uv run python test_transcriber.py

# Aider PTY interface
uv run python test_agent.py
```

## Known issues and workarounds

- **`webrtcvad` import error on Python 3.11+** — apply the `sed` patch in Setup step 2.
- **`libcublas.so.12` not found on Arch** — apply the symlink fix in Setup step 3.
- **Whisper mishears short/quiet utterances** — speak clearly and wait for a brief pause after finishing; VAD uses that silence to detect the end of an utterance.