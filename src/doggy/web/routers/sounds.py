from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import status as http_status

from doggy.core.config import Settings
from doggy.core.runtime import RuntimeSettings
from doggy.reaction.sound import Alerter

# Starlette renamed HTTP_422_UNPROCESSABLE_ENTITY -> _CONTENT (0.47); accept either
# (prefer the new name so current Starlette doesn't emit a deprecation warning).
_HTTP_422 = getattr(http_status, "HTTP_422_UNPROCESSABLE_CONTENT", None) or getattr(
    http_status, "HTTP_422_UNPROCESSABLE_ENTITY", 422
)
# Audio clips the UI may list and accept as uploads (pw-play/afplay-friendly).
_AUDIO_EXTS = {".wav", ".mp3", ".ogg"}


def build_router(settings: Settings, runtime: RuntimeSettings,
                 alerter: Alerter) -> APIRouter:
    router = APIRouter()

    @router.get("/api/sounds")
    def api_sounds() -> dict:
        clips_dir = Path(settings.clips_dir)
        sounds = sorted(
            p.name for p in clips_dir.glob("*")
            if p.is_file() and p.suffix.lower() in _AUDIO_EXTS
        ) if clips_dir.is_dir() else []
        return {"sounds": sounds, "selected": runtime.get().selected_sound}

    @router.post("/api/sounds")
    def api_upload_sound(file: UploadFile = File(...)) -> dict:
        # Path(...).name strips any directory components → no path traversal.
        name = Path(file.filename or "").name
        if Path(name).suffix.lower() not in _AUDIO_EXTS:
            raise HTTPException(status_code=_HTTP_422, detail="unsupported audio type")
        clips_dir = Path(settings.clips_dir)
        clips_dir.mkdir(parents=True, exist_ok=True)
        (clips_dir / name).write_bytes(file.file.read())
        return {"ok": True, "name": name}

    @router.post("/api/test-sound")
    def api_test_sound() -> dict:
        alerter.alert()
        return {"ok": True}

    return router
