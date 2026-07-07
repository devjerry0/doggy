from __future__ import annotations

import logging
import shutil
import subprocess
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("doggy")

# One talker at a time: the speaker is a single mono pipe, so a second caller is
# turned away rather than mixed in. Module-level because the appliance runs one
# process and the lock must outlive any single websocket.
_busy = threading.Lock()


def _spawn_player() -> subprocess.Popen | None:
    # Raw PCM straight into PipeWire; on a dev Mac there is no pw-cat, so we
    # return None and the handler discards audio (the UI still works).
    exe = shutil.which("pw-cat") or shutil.which("pw-play")
    if not exe:
        log.info("push-to-talk: no pw-cat on this host; discarding audio")
        return None
    return subprocess.Popen(
        [exe, "--playback", "--rate", "16000", "--channels", "1",
         "--format", "s16", "-"], stdin=subprocess.PIPE)


def build_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/talk")
    async def talk(ws: WebSocket) -> None:
        if not _busy.acquire(blocking=False):
            # Accept first so the browser gets a clean close code rather than a
            # bare handshake failure it can't distinguish from a network fault.
            await ws.accept()
            await ws.close(code=1013)  # try again later: someone is talking
            return
        proc = _spawn_player()
        try:
            await ws.accept()
            while True:
                data = await ws.receive_bytes()
                if proc and proc.stdin:
                    # Blocking write on the event loop: frames are tiny (~8 KB)
                    # and go to a local pipe, so it never meaningfully stalls.
                    proc.stdin.write(data)
                    proc.stdin.flush()
        except WebSocketDisconnect:
            pass
        finally:
            if proc:
                proc.stdin.close()
                proc.terminate()
            _busy.release()

    return router
