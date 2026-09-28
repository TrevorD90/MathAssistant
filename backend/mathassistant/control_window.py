"""The small "MathAssistant is running" window (spec §3.1, Phase 3).

The tutor runs in the browser, but a downloaded app needs something visible
that owns the server: closing this window (or the Quit button here or in
the browser) stops it. Uses tkinter from Python's standard library (PSF
license; Tcl/Tk is BSD-style), so no extra dependency.
"""

from __future__ import annotations

import logging
import sys
import webbrowser
from typing import Callable

log = logging.getLogger(__name__)


def available() -> bool:
    try:
        import tkinter  # noqa: F401

        return True
    except Exception:
        return False


def run(url: str, version: str, is_stopped: Callable[[], bool], stop: Callable[[], None]) -> None:
    """Show the window and block until it closes (must run on the main thread)."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("MathAssistant")
    root.resizable(False, False)
    root.geometry("340x150")

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="MathAssistant is running", font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
    ttk.Label(frame, text="It opens in your web browser. Close this\nwindow when you're done to stop it.",
              justify="left").pack(anchor="w", pady=(4, 10))

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")

    def quit_app() -> None:
        stop()
        root.destroy()

    ttk.Button(buttons, text="Open MathAssistant", command=lambda: webbrowser.open(url)).pack(side="left")
    ttk.Button(buttons, text="Quit", command=quit_app).pack(side="right")
    ttk.Label(frame, text=f"Version {version}", foreground="#777").pack(anchor="w", pady=(10, 0))

    root.protocol("WM_DELETE_WINDOW", quit_app)
    if sys.platform == "darwin":
        root.createcommand("tk::mac::Quit", quit_app)   # Cmd+Q / Dock "Quit"

    def poll() -> None:
        # The browser's Quit button stops the server; close the window too.
        if is_stopped():
            root.destroy()
            return
        root.after(500, poll)

    root.after(500, poll)
    root.mainloop()
