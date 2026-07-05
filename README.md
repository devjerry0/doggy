# 🐕 doggy

Local dog-presence detector: watches a USB webcam, plays a deterrent clip when a
dog is confirmed, and serves a localhost dashboard for live view + live tuning.

## Quick start (Mac dev)

    uv sync
    cp .env.example .env          # set DOGGY_CAMERA_INDEX (C922 is usually 1)
    uv run yolo export model=yolo26n.pt format=ncnn   # downloads yolo26n.pt
    # add at least one clip to sounds/
    uv run doggy                  # dashboard at http://127.0.0.1:8000

Grant your terminal camera permission (System Settings → Privacy → Camera) or
OpenCV returns empty frames silently.

## Config

Everything is set via `DOGGY_*` env vars (see `.env.example`). Live-tunable
params (confidence, confirm/cooldown, volume, safety) can also be changed from the
dashboard; structural params (camera, model, audio backend) need a restart.

## Raspberry Pi 5

- Use a USB webcam (the CSI ribbon camera is not supported in v1).
- Set a USB speaker as the default audio sink (Pi 5 has no 3.5mm jack).
- Export the model to NCNN for speed; install and run with `uv`.
- Run as a service: copy `systemd/doggy.service`, `systemctl enable --now doggy`.

## Tests

    uv run pytest -m "not slow"    # fast suite, no hardware/weights
    uv run pytest -m slow          # detector test (needs model + fixtures)

## License

AGPL-3.0-or-later (YOLO26n is AGPL; the whole project matches).
