"""Martin catalog helpers: wait for publish + optional on-demand container reload."""
from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def _catalog_url() -> str:
    base = (getattr(settings, "MARTIN_INTERNAL_URL", "") or "").rstrip("/")
    return f"{base}/catalog" if base else ""


def fetch_martin_catalog(timeout: float = 3.0) -> dict:
    url = _catalog_url()
    if not url:
        return {}
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def martin_has_source(table_name: str, catalog: dict | None = None) -> bool:
    if catalog is None:
        try:
            catalog = fetch_martin_catalog()
        except Exception:
            return False
    tiles = catalog.get("tiles") or {}
    return table_name in tiles


def restart_martin_container() -> bool:
    """Restart the Martin Docker container via the mounted docker.sock (optional).

    When ``MARTIN_DOCKER_CONTAINER`` is set, Django restarts Martin after
    upload/delete so new tables appear without continuous catalog polling.
    """
    name = (getattr(settings, "MARTIN_DOCKER_CONTAINER", "") or "").strip()
    sock_path = getattr(settings, "DOCKER_SOCKET", "/var/run/docker.sock")
    if not name:
        return False

    try:
        payload = (
            f"POST /containers/{name}/restart?t=3 HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Content-Length: 0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("ascii")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(20)
        sock.connect(sock_path)
        sock.sendall(payload)
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        sock.close()
        status_line = response.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
        ok = " 204" in status_line or " 200" in status_line or " 304" in status_line
        if ok:
            logger.info("Restarted Martin container %s", name)
        else:
            logger.warning("Martin restart unexpected response: %s", status_line)
        return ok
    except OSError as exc:
        logger.warning("Could not restart Martin via docker.sock: %s", exc)
        return False


def ensure_martin_source(table_name: str, timeout: float | None = None) -> bool:
    """Make sure Martin has published ``table_name``, restarting if configured.

    Cost profile:
    - Prefer on-demand container restart (no background catalog polling).
    - Otherwise rely on Martin's ``reload_interval`` (default 60s in entrypoint).
    - Poll ``/catalog`` sparingly (every 2s) only until ready or timeout.
    """
    if not _catalog_url():
        return False

    # Fast path: already published
    try:
        if martin_has_source(table_name):
            return True
    except Exception:
        pass

    restart_martin_container()

    timeout = timeout if timeout is not None else getattr(settings, "MARTIN_READY_TIMEOUT", 90)
    poll_every = float(getattr(settings, "MARTIN_READY_POLL_SECONDS", 2))
    deadline = time.monotonic() + max(timeout, 1)
    last_error = None

    while time.monotonic() < deadline:
        try:
            if martin_has_source(table_name):
                logger.info("Martin published tile source %s", table_name)
                return True
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = exc
        time.sleep(max(poll_every, 0.5))

    logger.warning(
        "Martin did not publish %s within %ss (last error: %s).",
        table_name,
        timeout,
        last_error,
    )
    return False


# Backwards-compatible alias
wait_for_martin_source = ensure_martin_source
