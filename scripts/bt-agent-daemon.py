#!/usr/bin/env python3
"""Persistent BlueZ agent + reconnect loop for a keyless ("Just Works") BT speaker.

WHY THIS EXISTS
---------------
Cheap A2DP speakers (e.g. the JBL Go 5) pair as *No Bonding*: when the kernel
emits the New Link Key event it sets ``store_hint=0``, so BlueZ deliberately
never writes a ``[LinkKey]`` into ``/var/lib/bluetooth/.../info``. The bond is
alive for the current boot only — after a reboot the device is ``Paired: no``
and a plain ``connect`` fails with ``br-connection-unknown``. This is a property
of the *speaker's* firmware and is NOT fixable by how you drive ``bluetoothctl``
(we verified: one-shot, kept-alive pipe, and a real PTY all yield store_hint=0).

The workaround that DOES survive reboots: keep a ``NoInputNoOutput`` pairing
agent registered at all times so that when the connection is (re)established the
fresh Just-Works re-pair is auto-accepted, plus ``JustWorksRepairing = always``
in ``/etc/bluetooth/main.conf`` and a trusted device. A single long-lived
``bluetoothctl`` inside a PTY keeps that agent alive for the whole uptime; the
loop re-asserts the connection whenever it drops.

The speaker MAC comes from ``$DOGGY_BT_MAC`` or argv[1].
"""
import os
import pty
import select
import sys
import time

MAC = os.environ.get("DOGGY_BT_MAC") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not MAC:
    sys.exit("usage: DOGGY_BT_MAC=AA:BB:.. bt-agent-daemon.py   (or pass MAC as argv[1])")

pid, fd = pty.fork()  # child gets a real controlling TTY -> interactive bluetoothctl
if pid == 0:
    os.execvp("bluetoothctl", ["bluetoothctl"])


def send(cmd: str) -> None:
    try:
        os.write(fd, (cmd + "\n").encode())
    except OSError:
        pass


def drain(seconds: float) -> str:
    """Read (and discard) bluetoothctl output for `seconds`, returning what we saw."""
    end = time.time() + seconds
    out = b""
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            try:
                d = os.read(fd, 4096)
            except OSError:
                return out.decode(errors="replace")
            if not d:
                return out.decode(errors="replace")
            out += d
    return out.decode(errors="replace")


# Register the agent ONCE; keeping this process alive keeps the agent registered.
send("power on")
drain(1)
send("agent NoInputNoOutput")
drain(1)
send("default-agent")
drain(1)

while True:
    drain(25)
    send("info " + MAC)
    if "Connected: yes" not in drain(2):
        send("connect " + MAC)
        drain(6)
