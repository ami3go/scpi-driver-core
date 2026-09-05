"""HTTP helper API for discovery, calibration download, and LED identify."""
from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request

from .exceptions import HttpApiError

_LOG = logging.getLogger(__name__)


class EResistorHttpApi:
    def __init__(self, host: str, port: int = 80, *, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def get_text(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:  # noqa: S310 - device URL supplied by user
                raw = resp.read(1024 * 1024)
                return raw.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HttpApiError(f"HTTP GET {url} failed: {exc}") from exc

    def ping(self) -> bool:
        try:
            return self.get_text("/ping").strip().lower() == "pong"
        except HttpApiError:
            return False

    def state(self) -> str:
        return self.get_text("/state")

    def identify_led(self) -> str:
        return self.get_text("/identify_led")

    def list_calibration_files(self) -> str:
        return self.get_text("/api/calibration/files")

    def download_channel_calibration(self, channel: int) -> str:
        query = urllib.parse.urlencode({"ch": str(channel)})
        return self.get_text(f"/api/calibration/download?{query}")

    def download_all_calibration(self) -> str:
        return self.get_text("/api/calibration/download_all")
