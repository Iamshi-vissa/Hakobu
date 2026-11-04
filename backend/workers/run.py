"""Worker entry point: warm LibreOffice instances + an RQ worker pool sized to the CPUs.

Run with ``python -m workers.run``.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

from rq.worker_pool import WorkerPool

from app.config import get_settings
from app.redis_client import get_redis
from engines.media import H264_ENV, detect_h264_encoder
from engines.office import profile_uri

log = logging.getLogger("hakobu.worker")

UNO_PORT_OFFSET = 100  # internal UNO socket = XML-RPC port + offset
STARTUP_TIMEOUT = 60.0
RECYCLE_AFTER = 250  # conversions per LibreOffice process


def _start_unoserver(slot: int) -> subprocess.Popen[bytes]:
    settings = get_settings()
    port = settings.unoserver_base_port + slot
    return subprocess.Popen(  # noqa: S603 - fixed argv
        [
            sys.executable, "-m", "unoserver.server",
            "--interface", settings.unoserver_host, "--port", str(port),
            "--uno-port", str(port + UNO_PORT_OFFSET),
            "--user-installation", profile_uri(slot),
            "--conversion-timeout", str(settings.subprocess_timeout_seconds),
            # Recycle LibreOffice periodically to contain leaks; the supervisor restarts it.
            "--stop-after", str(RECYCLE_AFTER),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _wait_for_port(port: int) -> bool:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            if sock.connect_ex((get_settings().unoserver_host, port)) == 0:
                return True
        time.sleep(0.5)
    return False


def _supervise(slots: int) -> None:
    """Start warm LibreOffice instances and restart any that die."""
    base = get_settings().unoserver_base_port
    procs = {slot: _start_unoserver(slot) for slot in range(slots)}
    for slot in procs:
        if not _wait_for_port(base + slot):
            log.warning("unoserver slot %d did not come up within %ss", slot, STARTUP_TIMEOUT)

    def watch() -> None:
        while True:
            for slot, proc in procs.items():
                if proc.poll() is not None:
                    log.warning("unoserver slot %d exited (%s); restarting", slot, proc.returncode)
                    procs[slot] = _start_unoserver(slot)
            time.sleep(2)

    threading.Thread(target=watch, name="unoserver-supervisor", daemon=True).start()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if settings.unoserver_instances and shutil.which("soffice"):
        _supervise(settings.unoserver_instances)
        log.info("started %d warm LibreOffice instance(s)", settings.unoserver_instances)
    # Probe hardware encoders once; forked work horses inherit the answer via the env.
    os.environ[H264_ENV] = detect_h264_encoder()
    log.info("H.264 encoder: %s", os.environ[H264_ENV])
    log.info("starting %d RQ workers on queue %r", settings.worker_concurrency, settings.queue_name)
    WorkerPool([settings.queue_name], connection=get_redis(),
               num_workers=settings.worker_concurrency).start()


if __name__ == "__main__":
    main()
