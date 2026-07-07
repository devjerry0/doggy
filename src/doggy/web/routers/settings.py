from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi import status as http_status
from pydantic import ValidationError

from doggy.core.config import TunableSettings
from doggy.core.runtime import RuntimeSettings

# Starlette renamed HTTP_422_UNPROCESSABLE_ENTITY -> _CONTENT (0.47); accept either
# (prefer the new name so current Starlette doesn't emit a deprecation warning).
_HTTP_422 = getattr(http_status, "HTTP_422_UNPROCESSABLE_CONTENT", None) or getattr(
    http_status, "HTTP_422_UNPROCESSABLE_ENTITY", 422
)


def build_router(runtime: RuntimeSettings,
                 save_env: Callable[[TunableSettings], None]) -> APIRouter:
    router = APIRouter()

    @router.patch("/api/settings")
    def api_patch(patch: dict) -> dict:
        merged = {**runtime.get().model_dump(), **patch}
        try:
            updated = TunableSettings(**merged)
        except ValidationError as exc:
            raise HTTPException(status_code=_HTTP_422, detail=str(exc)) from exc
        runtime.update(updated)
        return updated.model_dump(mode="json")

    @router.post("/api/settings/save")
    def api_save() -> dict:
        save_env(runtime.get())
        return {"ok": True}

    return router
