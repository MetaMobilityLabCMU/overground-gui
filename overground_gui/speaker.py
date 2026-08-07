"""Optional text-to-speech for naming coordinates."""

from __future__ import annotations

import threading
from typing import Optional


class Speaker:
    """Thread-safe TTS wrapper. Speaks on a background thread so the UI stays responsive."""

    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()
        self._available = False
        self._init_engine()

    def _init_engine(self) -> None:
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 160)
            self._available = True
        except Exception:
            self._engine = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def speak(self, text: str) -> None:
        if not self._available or not self._engine:
            return
        threading.Thread(target=self._speak_sync, args=(text,), daemon=True).start()

    def _speak_sync(self, text: str) -> None:
        with self._lock:
            try:
                assert self._engine is not None
                self._engine.stop()
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception:
                # Attempt one re-init if the engine dies mid-session
                try:
                    self._init_engine()
                    if self._engine:
                        self._engine.say(text)
                        self._engine.runAndWait()
                except Exception:
                    self._available = False
