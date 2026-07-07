from __future__ import annotations

import time

from fastapi import APIRouter

from doggy.decision.gate import FireGate


def build_router(gate: FireGate) -> APIRouter:
    router = APIRouter()

    @router.post("/api/snooze")
    def api_snooze(body: dict) -> dict:
        # Monotonic clock so the snooze timeline matches the pipeline's gate.allow.
        gate.snooze(float(body["minutes"]) * 60, time.monotonic())
        return {"ok": True}

    @router.post("/api/snooze/cancel")
    def api_snooze_cancel() -> dict:
        gate.cancel_snooze()
        return {"ok": True}

    return router
