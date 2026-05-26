"""
voice_agent.py
--------------
Multithreaded design:

  Thread 1 (main):     wake word → mic → VAD → Whisper → queue
  Thread 2 (worker):   queue → aider

Flow:
  1. Say "Hey Jarvis" to activate
  2. Speak your coding request
  3. Whisper transcribes and sends to aider
  4. Aider responds on screen, files dropped from context
  5. System returns to sleeping state
"""
import suppress_alsa
_saved_stderr = suppress_alsa.apply()

import os
import sys
import time
import threading
import queue

from rich.console import Console
from audio_capture import MicrophoneStream      # PyAudio loads here
from transcriber import Transcriber
from agent_interface import AiderInterface, _warm_up_ollama
from wake_word import WakeWordDetector          # openwakeword loads here

# Restore stderr now that all C libraries have initialized
if _saved_stderr is not None:
    os.dup2(_saved_stderr, 2)
    os.close(_saved_stderr)

console = Console()
# ... rest of file unchanged

# ── Config ─────────────────────────────────────────────────────────────────────
WHISPER_MODEL  = "medium"
WHISPER_DEVICE = "cuda"
AIDER_MODEL    = "ollama/qwen2.5-coder:7b"

EXIT_PHRASES  = {"exit", "quit", "stop", "stop listening", "goodbye", "bye"}
CLEAR_PHRASES = {"new session", "new chat", "start over", "reset"}

SLASH_COMMANDS = {
    "undo that":      "/undo",
    "undo":           "/undo",
    "show diff":      "/diff",
    "git diff":       "/diff",
    "clear chat":     "/clear",
    "clear context":  "/clear",
    "run the code":   "/run",
    "run tests":      "/test",
    "run the tests":  "/test",
    "commit this":    "/commit",
    "commit":         "/commit",
    "show files":     "/ls",
    "list files":     "/ls",
    "drop all files": "/drop",
    "drop all":       "/drop",
}

# Set when aider is processing — wake word triggers ignored during this time
aider_busy = threading.Event()


def resolve_command(text: str):
    """Map natural speech to aider slash commands."""
    text_lower = text.lower().strip(" .,!")

    if text_lower in SLASH_COMMANDS:
        return SLASH_COMMANDS[text_lower]

    if text_lower.startswith("add "):
        filename = (text_lower[4:]
                    .replace(" to context", "")
                    .replace(" to chat", "")
                    .strip())
        if filename:
            return f"/add {filename}"

    if text_lower.startswith("drop "):
        filename = text_lower[5:].strip()
        if filename and filename not in ("all", "all files"):
            return f"/drop {filename}"

    return None


def aider_worker(
    agent: AiderInterface,
    text_queue: queue.Queue,
    stop_event: threading.Event,
):
    """
    Worker thread: drains text_queue and sends each item to aider.
    Sets aider_busy while processing to block wake word re-triggers.
    """
    while not stop_event.is_set():
        try:
            text = text_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        aider_busy.set()
        console.print(f"\n[bold yellow]→ aider:[/bold yellow] {text}\n")
        try:
            is_slash = text.startswith("/")
            agent.send_and_wait(text, timeout=120, auto_drop=not is_slash)
        except Exception as e:
            console.print(f"[red]Aider error: {e}[/red]")
        finally:
            time.sleep(2)  # brief pause before allowing wake word again
            aider_busy.clear()

        text_queue.task_done()


def _restart_aider(agent, text_queue, stop_event, worker):
    """Cleanly stop aider and worker, start fresh ones."""
    with text_queue.mutex:
        text_queue.queue.clear()
    stop_event.set()
    worker.join(timeout=3)
    agent.stop()
    time.sleep(1)

    new_agent  = AiderInterface(model=AIDER_MODEL)
    new_agent.start()
    new_stop   = threading.Event()
    new_worker = threading.Thread(
        target=aider_worker,
        args=(new_agent, text_queue, new_stop),
        daemon=True,
    )
    new_worker.start()
    return new_agent, new_stop, new_worker


def main():
    console.print("\n[bold cyan]voice-aider[/bold cyan] — speak to code\n")
    console.print(f"  STT      : Whisper [yellow]{WHISPER_MODEL}[/yellow] on [yellow]{WHISPER_DEVICE}[/yellow]")
    console.print(f"  Agent    : [yellow]{AIDER_MODEL}[/yellow]")
    console.print(f"  Wake word: [yellow]'Hey Jarvis'[/yellow]")
    console.print("\n  Say [bold]'exit'[/bold] or Ctrl+C to quit.\n")

    # ── 1. Warm up ollama (loads LLM into VRAM before Whisper) ────────────────
    console.print("[dim]Warming up ollama...[/dim]")
    _warm_up_ollama(AIDER_MODEL)

    # ── 2. Load Whisper ───────────────────────────────────────────────────────
    console.print("[dim]Loading Whisper...[/dim]")
    transcriber = Transcriber(model_size=WHISPER_MODEL, device=WHISPER_DEVICE)
    console.print("[dim]Whisper ready.[/dim]\n")

    # ── 3. Load wake word detector (CPU only) ─────────────────────────────────
    detector = WakeWordDetector()
    detector.load()

    # ── 4. Start aider ────────────────────────────────────────────────────────
    console.print("[dim]Starting aider...[/dim]")
    agent = AiderInterface(model=AIDER_MODEL)
    agent.start()

    if not agent.is_alive():
        console.print("[red]ERROR: Aider died on startup.[/red]")
        return

    # ── 5. Start worker thread ────────────────────────────────────────────────
    text_queue = queue.Queue()
    stop_event = threading.Event()
    worker = threading.Thread(
        target=aider_worker,
        args=(agent, text_queue, stop_event),
        daemon=True,
    )
    worker.start()

    console.print("\n[bold]Say [cyan]'Hey Jarvis'[/cyan] to activate.[/bold]\n")

    # ── 6. Main loop ───────────────────────────────────────────────────────────
    try:
        while True:
            sys.stderr.write("\r🔇 [sleeping]  say 'Hey Jarvis' to activate       \r")
            sys.stderr.flush()

            detector.wait_for_wake_word()

            if aider_busy.is_set():
                continue

            # Pause before opening mic — lets "Jarvis" sound pass
            time.sleep(1.2)

            console.print("\n[bold cyan]⚡ Hey Jarvis![/bold cyan] Listening...\n")

            text = ""
            try:
                with MicrophoneStream() as mic:
                    for utterance in mic.utterances():
                        sys.stderr.write("\r[transcribing...]                       \r")
                        sys.stderr.flush()
                        text = transcriber.transcribe(utterance)
                        break
            except Exception as e:
                console.print(f"[red]Mic error: {e}[/red]")
                continue

            if not text or len(text.split()) < 2:
                console.print("[dim]Didn't catch that — say 'Hey Jarvis' and try again.[/dim]\n")
                continue

            console.print(f"[bold green]You:[/bold green] {text}")

            text_lower = text.lower().strip(" .,!")

            if text_lower in EXIT_PHRASES:
                console.print("[dim]Shutting down...[/dim]")
                break

            if text_lower in CLEAR_PHRASES:
                agent, stop_event, worker = _restart_aider(
                    agent, text_queue, stop_event, worker
                )
                console.print("[dim]New session started.[/dim]\n")
                continue

            slash = resolve_command(text)
            if slash:
                console.print(f"[dim]→ slash command: {slash}[/dim]")
                text_queue.put(slash)
                continue

            text_queue.put(text)

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as e:
        import traceback
        console.print(f"[red]Crash: {e}[/red]")
        traceback.print_exc()
    finally:
        stop_event.set()
        worker.join(timeout=3)
        agent.stop()
        console.print("\n[bold cyan]voice-aider[/bold cyan] stopped.\n")


if __name__ == "__main__":
    main()