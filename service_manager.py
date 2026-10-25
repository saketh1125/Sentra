"""Small desktop controller for Sentra's Docker Compose services."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
POLL_SECONDS = 3


class ServiceManager(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sentra Service Manager")
        self.geometry("620x430")
        self.minsize(520, 360)
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        self.closing = False

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Sentra", font=("TkDefaultFont", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Local services", font=("TkDefaultFont", 10)).pack(anchor="w", pady=(0, 14))

        status = ttk.LabelFrame(frame, text="Live status", padding=10)
        status.pack(fill="x")
        self.api_status = tk.StringVar(value="Checking…")
        self.db_status = tk.StringVar(value="Checking…")
        ttk.Label(status, text="API · http://127.0.0.1:8000/ready").grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Label(status, textvariable=self.api_status, width=20).grid(row=0, column=1, sticky="w")
        ttk.Label(status, text="Database · PostgreSQL").grid(row=1, column=0, sticky="w", padx=(0, 16), pady=(6, 0))
        ttk.Label(status, textvariable=self.db_status, width=20).grid(row=1, column=1, sticky="w", pady=(6, 0))

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=12)
        self.start_button = ttk.Button(controls, text="Start services", command=self.start_services)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Stop services", command=self.stop_services)
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Open web app", command=self.open_web).pack(side="right")

        ttk.Label(frame, text="Service output").pack(anchor="w")
        self.output = tk.Text(frame, height=12, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, pady=(5, 0))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(200, self.drain_events)
        self.after(0, self.poll_status)

    def append(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def run_compose(self, action: str) -> None:
        if self.busy:
            return
        self.busy = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.append(f"\n$ docker compose {action}\n")

        def worker() -> None:
            try:
                proc = subprocess.Popen(
                    ["docker", "compose", *action.split()], cwd=ROOT,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.events.put(("output", line))
                code = proc.wait()
                self.events.put(("done", f"Compose command finished with exit code {code}.\n"))
            except OSError as exc:
                self.events.put(("done", f"Could not run Docker Compose: {exc}\n"))

        threading.Thread(target=worker, daemon=True).start()

    def start_services(self) -> None:
        self.run_compose("up --build -d")

    def stop_services(self) -> None:
        self.run_compose("stop")

    def poll_status(self) -> None:
        if self.closing:
            return

        def worker() -> None:
            try:
                with urlopen("http://127.0.0.1:8000/ready", timeout=2) as response:
                    import json
                    payload = json.loads(response.read().decode())
                api = "Ready" if payload.get("status") == "ready" else "Degraded"
                db = "Ready" if payload.get("db") == "ok" else "Unavailable"
            except (URLError, TimeoutError, ValueError, OSError):
                api, db = "Stopped / starting", "Unknown"
            self.events.put(("status", f"{api}\t{db}"))

        threading.Thread(target=worker, daemon=True).start()
        self.after(POLL_SECONDS * 1000, self.poll_status)

    def drain_events(self) -> None:
        if self.closing:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "output":
                    self.append(value)
                elif kind == "done":
                    self.append(value)
                    self.busy = False
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="normal")
                elif kind == "status":
                    api, db = value.split("\t")
                    self.api_status.set(api)
                    self.db_status.set(db)
        except queue.Empty:
            pass
        self.after(200, self.drain_events)

    def open_web(self) -> None:
        import webbrowser
        webbrowser.open("http://localhost:5173")

    def close(self) -> None:
        self.closing = True
        self.destroy()


if __name__ == "__main__":
    ServiceManager().mainloop()
