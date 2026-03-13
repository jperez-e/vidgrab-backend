from __future__ import annotations

import json
import os
import threading
from typing import Dict
from uuid import uuid4

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv

load_dotenv()


from downloader import get_video_info, download_video, sanitize_filename, validate_url
from progress import (
    init_progress,
    update_progress,
    get_progress,
    set_filename,
    remove_progress,
)

app = FastAPI(title="VidGrab API")

allowed_origins = [
    "https://jperez-e.github.io",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

download_semaphore = threading.Semaphore(5)
download_paths: Dict[str, str] = {}


@app.get("/")
def root() -> Dict[str, str]:
    return {"status": "ok", "service": "VidGrab API"}


@app.get("/info")
def info(url: str) -> JSONResponse:
    try:
        validate_url(url)
        data = get_video_info(url)
        return JSONResponse(content=data)
    except ValueError as exc:
        status = 400 if "URL inválida" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al analizar: {exc}") from exc


@app.post("/download")
def download(body: Dict[str, str], background: BackgroundTasks) -> JSONResponse:
    url = body.get("url", "")
    quality = body.get("quality", "720p")
    if not url:
        raise HTTPException(status_code=400, detail="URL inválida.")
    try:
        validate_url(url)
        info = get_video_info(url)
    except ValueError as exc:
        status = 400 if "URL inválida" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al analizar: {exc}") from exc

    job_id = str(uuid4())
    filename = f"{sanitize_filename(info['title'])}.mp4"
    init_progress(job_id, filename)
    set_filename(job_id, filename)

    def run_download() -> None:
        with download_semaphore:
            try:
                update_progress(job_id, 1.0, "Iniciando...")
                path = download_video(url, quality, job_id)
                download_paths[job_id] = path
                update_progress(job_id, 100.0, "done")
            except Exception as exc:
                update_progress(job_id, 0.0, f"error: {exc}")

    background.add_task(run_download)
    return JSONResponse(status_code=202, content={"job_id": job_id, "filename": filename})


@app.get("/progress/{job_id}")
def progress(job_id: str) -> EventSourceResponse:
    initial = get_progress(job_id)
    if initial.get("status") == "desconocido":
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    async def event_generator():
        while True:
            data = get_progress(job_id)
            yield {
                "event": "message",
                "data": json.dumps({"percent": data["percent"], "status": data["status"]}),
            }
            if data["status"] == "done" or str(data["status"]).startswith("error"):
                yield {"event": "done", "data": json.dumps({"status": data["status"]})}
                break
            await asyncio_sleep(0.5)

    return EventSourceResponse(event_generator())


@app.get("/file/{job_id}")
def file(job_id: str, background: BackgroundTasks) -> FileResponse:
    path = download_paths.get(job_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no disponible.")

    progress_data = get_progress(job_id)
    filename = progress_data.get("filename", "video.mp4")

    def cleanup() -> None:
        if os.path.exists(path):
            os.remove(path)
        download_paths.pop(job_id, None)
        remove_progress(job_id)

    background.add_task(cleanup)
    return FileResponse(path, filename=filename, media_type="video/mp4")


async def asyncio_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
