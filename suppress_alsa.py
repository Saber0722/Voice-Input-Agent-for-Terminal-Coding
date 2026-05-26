"""
suppress_alsa.py
----------------
Silences ALSA error spam by redirecting stderr at the OS level
permanently at process startup, before any audio library loads.
"""
import os

def apply():
    try:
        # Open /dev/null for writing
        devnull = os.open(os.devnull, os.O_WRONLY)
        # Save original stderr fd
        saved = os.dup(2)
        # Point fd 2 to /dev/null
        os.dup2(devnull, 2)
        os.close(devnull)
        # Restore stderr after a tiny delay — just enough for
        # all audio library C-level initialization to complete
        # We restore it after imports in voice_agent.py
        # Store saved fd so caller can restore
        return saved
    except Exception:
        return None