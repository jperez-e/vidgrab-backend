from __future__ import annotations

import threading
from typing import Dict, Any

progress_store: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def init_progress(job_id: str, filename: str) -> None:
    with _lock:
        progress_store[job_id] = {
            "percent": 0.0,
            "status": "Esperando...",
            "filename": filename,
        }


def update_progress(job_id: str, percent: float, status: str) -> None:
    with _lock:
        if job_id in progress_store:
            progress_store[job_id]["percent"] = percent
            progress_store[job_id]["status"] = status


def get_progress(job_id: str) -> Dict[str, Any]:
    with _lock:
        return progress_store.get(job_id, {"percent": 0.0, "status": "desconocido"})


def set_filename(job_id: str, filename: str) -> None:
    with _lock:
        if job_id in progress_store:
            progress_store[job_id]["filename"] = filename


def remove_progress(job_id: str) -> None:
    with _lock:
        progress_store.pop(job_id, None)
