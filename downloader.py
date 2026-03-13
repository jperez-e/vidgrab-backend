from __future__ import annotations

import os
import re
import tempfile
import shutil
from typing import Dict, List
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from progress import update_progress

SUPPORTED_DOMAINS = [
    "tiktok.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "fb.watch",
    "threads.net",
    "threads.com",
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
    if "tiktok" in domain:
        return "TikTok"
    if "instagram" in domain:
        return "Instagram"
    if "twitter" in domain or domain == "x.com":
        return "Twitter / X"
    if "facebook" in domain or "fb.watch" in domain:
        return "Facebook"
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


def _get_cookiefile() -> str | None:
    cookie_path = os.getenv("COOKIES_PATH")
    if not cookie_path:
        return None
    tmp_path = os.path.join(tempfile.gettempdir(), "cookies.txt")
    try:
        shutil.copyfile(cookie_path, tmp_path)
        return tmp_path
    except Exception:
        return cookie_path


def _pick_thumbnail(info: Dict) -> str:
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        for item in reversed(thumbnails):
            if item.get("url"):
                return item["url"]
    return info.get("thumbnail") or ""


def get_video_info(url: str) -> Dict:
    domain = validate_url(url)
    platform = _platform_from_domain(domain)
    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best",
        "cookiefile": _get_cookiefile(),
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
        "thumbnail": _pick_thumbnail(info),
        "duration": int(info.get("duration") or 0),
        "platform": platform,
        "formats": available or ["360p"],
    }


def download_video(url: str, quality: str, job_id: str) -> str:
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

    if quality == "mp3":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
            "ffmpeg_location": os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg"),
            "cookiefile": _get_cookiefile(),
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
        }
    else:
        format_string = QUALITY_MAP.get(quality, QUALITY_MAP["720p"])
        ydl_opts = {
            "format": format_string,
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
            "ffmpeg_location": os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg"),
            "cookiefile": _get_cookiefile(),
        }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    final_ext = "mp3" if quality == "mp3" else "mp4"
    final_path = os.path.join(output_dir, f"{job_id}.{final_ext}")
    if not os.path.exists(final_path):
        raise FileNotFoundError("Archivo final no encontrado.")
    return final_path
