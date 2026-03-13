from __future__ import annotations

import os
import re
import tempfile
from typing import Dict, List
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from progress import update_progress

SUPPORTED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "fb.watch",
    "twitch.tv",
    "threads.net",
]

QUALITY_MAP = {
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
}


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL inválida.")
    host = parsed.netloc.lower()
    host = host.replace("www.", "")
    return host


def _platform_from_domain(domain: str) -> str:
    if "youtube" in domain or "youtu.be" in domain:
        return "YouTube"
    if "tiktok" in domain:
        return "TikTok"
    if "instagram" in domain:
        return "Instagram"
    if "twitter" in domain or domain == "x.com":
        return "Twitter / X"
    if "facebook" in domain or "fb.watch" in domain:
        return "Facebook"
    if "twitch" in domain:
        return "Twitch"
    if "threads" in domain:
        return "Threads"
    return "Desconocido"


def validate_url(url: str) -> str:
    domain = _domain_from_url(url)
    if not any(domain.endswith(d) for d in SUPPORTED_DOMAINS):
        raise ValueError("Plataforma no soportada.")
    return domain


def sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^\w\-. ]+", "", name, flags=re.UNICODE)
    safe = safe.strip()[:80] or "video"
    return safe


def get_video_info(url: str) -> Dict:
    domain = validate_url(url)
    platform = _platform_from_domain(domain)
    ydl_opts = {
    "skip_download": True,
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "format": "best",
}

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    formats = info.get("formats", [])
    heights = sorted({f.get("height") for f in formats if f.get("height")})
    targets = [360, 720, 1080, 2160]
    available = [f"{t}p" for t in targets if any(h == t for h in heights)]
    if not available and heights:
        max_height = max(heights)
        fallback = max([t for t in targets if t <= max_height], default=360)
        available = [f"{fallback}p"]
    return {
        "title": info.get("title") or "Video",
        "thumbnail": info.get("thumbnail") or "",
        "duration": int(info.get("duration") or 0),
        "platform": platform,
        "formats": available or ["360p"],
    }


def download_video(url: str, quality: str, job_id: str) -> str:
    format_string = QUALITY_MAP.get(quality, QUALITY_MAP["720p"])
    output_dir = tempfile.gettempdir()
    output_template = os.path.join(output_dir, f"{job_id}.%(ext)s")

    def progress_hook(data: Dict) -> None:
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else 0
            update_progress(job_id, percent, "Descargando...")
        elif status == "finished":
            update_progress(job_id, 98.0, "Procesando con ffmpeg...")

    ydl_opts = {
        "format": format_string,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "ffmpeg_location": os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg"),
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    final_path = os.path.join(output_dir, f"{job_id}.mp4")
    if not os.path.exists(final_path):
        raise FileNotFoundError("Archivo final no encontrado.")
    return final_path
