"""
agent_interface.py
------------------
Spawns aider as a subprocess with stdin/stdout pipes.
--no-pretty disables aider's TUI so it works cleanly with pipes.
Output is streamed line by line in a background thread.
After each response, /drop clears aider's file context so the
next request starts fresh.
"""

import os
import sys
import subprocess
import threading
import urllib.request
import json


def _warm_up_ollama(model: str):
    """Force ollama to load the model into VRAM before Whisper starts."""
    model_name = model.replace("ollama/", "")
    payload = json.dumps({
        "model": model_name,
        "prompt": "hi",
        "stream": False
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=60)
        print("[voice-aider] Ollama model warmed up.")
    except Exception as e:
        print(f"[voice-aider] Ollama warmup warning: {e}")


class AiderInterface:
    def __init__(self, model: str = "ollama/qwen2.5-coder:7b", extra_args: list = None):
        self._proc       = None
        self.model       = model
        self.extra_args  = extra_args or []
        self._out_thread = None
        self._ready      = threading.Event()

    def _stream_output(self):
        """
        Reads aider's stdout line by line and prints it.
        Sets self._ready when aider's bare input prompt "> " is detected,
        indicating aider has finished responding and is ready for input.
        """
        for line in self._proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            stripped = line.strip()
            if stripped == ">" or stripped == "> ":
                self._ready.set()

    def start(self):
        env = {**os.environ, "OLLAMA_API_BASE": "http://localhost:11434"}

        cmd = [
            "aider",
            "--model",   self.model,
            "--no-show-model-warnings",
            "--no-gitignore",
            "--yes-always",
            "--no-pretty",
            "--no-stream",
        ] + (self.extra_args or [])

        print(f"[voice-aider] Launching: {' '.join(cmd)}\n")

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        self._ready.clear()
        self._out_thread = threading.Thread(
            target=self._stream_output, daemon=True
        )
        self._out_thread.start()

        # Wait for aider's first prompt
        self._ready.wait(timeout=15)
        self._ready.clear()

    def send_and_wait(self, text: str, timeout: int = 120, auto_drop: bool = True):
        if not self._proc or self._proc.poll() is not None:
            raise RuntimeError("Aider process is not running.")

        self._ready.clear()
        self._proc.stdin.write(text + "\n")
        self._proc.stdin.flush()
        self._ready.wait(timeout=timeout)
        self._ready.clear()

        # Only drop files after actual code requests, not slash commands
        if auto_drop and not text.startswith("/"):
            self._proc.stdin.write("/drop\n")
            self._proc.stdin.flush()
            self._ready.wait(timeout=10)
            self._ready.clear()

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write("/exit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.terminate()