from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import status as http_status

from doggy.core.config import Settings

# Starlette renamed HTTP_413_REQUEST_ENTITY_TOO_LARGE -> _CONTENT_TOO_LARGE (0.47);
# accept either (prefer the new name so current Starlette stays warning-free).
_HTTP_413 = getattr(http_status, "HTTP_413_CONTENT_TOO_LARGE", None) or getattr(
    http_status, "HTTP_413_REQUEST_ENTITY_TOO_LARGE", 413
)

# Calm audio the library lists and accepts as uploads.
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg"}
_CHUNK = 1024 * 1024          # stream uploads a MiB at a time (1 GB files won't fit RAM)
_PART_NAME = ".upload.part"   # dotfile: never listed as a track, replaced on success


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    def _dir() -> Path:
        return Path(settings.soothing_dir)

    def _tracks(soothing: Path) -> list[Path]:
        if not soothing.is_dir():
            return []
        return sorted(
            (p for p in soothing.glob("*")
             if p.is_file() and not p.name.startswith(".")
             and p.suffix.lower() in _AUDIO_EXTS),
            key=lambda p: p.name,
        )

    @router.get("/api/soothing")
    def api_soothing() -> dict:
        tracks = _tracks(_dir())
        sizes = [(p.name, p.stat().st_size) for p in tracks]
        return {
            "tracks": [{"name": n, "size": s} for n, s in sizes],
            "total_bytes": sum(s for _, s in sizes),
            "limit_bytes": settings.soothing_limit_bytes,
        }

    @router.post("/api/soothing")
    async def api_upload_soothing(file: UploadFile = File(...)) -> dict:
        # Path(...).name strips any directory components → no path traversal.
        name = Path(file.filename or "").name
        if Path(name).suffix.lower() not in _AUDIO_EXTS:
            raise HTTPException(
                status_code=http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="unsupported audio type")
        soothing = _dir()
        soothing.mkdir(parents=True, exist_ok=True)
        existing = sum(p.stat().st_size for p in _tracks(soothing))
        limit = settings.soothing_limit_bytes
        part = soothing / _PART_NAME
        written = 0
        with part.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                if existing + written + len(chunk) > limit:
                    out.close()
                    part.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=_HTTP_413,
                        detail="That would go over the 1 GB limit. Delete a track first.")
                out.write(chunk)
                written += len(chunk)
        os.replace(part, soothing / name)
        return {"name": name}

    @router.delete("/api/soothing/{name}")
    def api_delete_soothing(name: str) -> dict:
        # Path(name).name strips any directory components → no path traversal.
        path = _dir() / Path(name).name
        if not path.is_file():
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND,
                                detail="not found")
        path.unlink()
        return {"ok": True}

    return router
