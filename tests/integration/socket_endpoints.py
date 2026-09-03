"""Small loopback endpoints used by socket transport integration tests."""

from __future__ import annotations

import socket
import threading
from contextlib import suppress


class TcpEndpoint:
    def __init__(self) -> None:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(2)
        self.address = self.listener.getsockname()
        self.accepted = threading.Event()
        self.received = bytearray()
        self._connection: socket.socket | None = None
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self.listener.settimeout(0.05)
        while not self._closed.is_set():
            try:
                connection, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            self._connection = connection
            connection.settimeout(0.05)
            self.accepted.set()
            while not self._closed.is_set():
                try:
                    data = connection.recv(65_536)
                except TimeoutError:
                    continue
                except OSError:
                    break
                if not data:
                    break
                self.received.extend(data)
            with suppress(OSError):
                connection.close()

    def send(self, data: bytes) -> None:
        assert self.accepted.wait(timeout=2)
        assert self._connection is not None
        self._connection.sendall(data)

    def disconnect(self) -> None:
        if not self.accepted.wait(timeout=0.1):
            return
        if self._connection is not None:
            with suppress(OSError):
                self._connection.shutdown(socket.SHUT_RDWR)
            self._connection.close()

    def close(self) -> None:
        self._closed.set()
        self.disconnect()
        self.listener.close()
        self._thread.join(timeout=2)


class UdpEndpoint:
    def __init__(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.settimeout(0.05)
        self.address = self.socket.getsockname()
        self.received: list[tuple[bytes, tuple[str, int]]] = []
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                data, source = self.socket.recvfrom(65_536)
            except TimeoutError:
                continue
            except OSError:
                break
            self.received.append((data, source))

    def send(self, data: bytes, destination: tuple[str, int]) -> None:
        self.socket.sendto(data, destination)

    def close(self) -> None:
        self._closed.set()
        self.socket.close()
        self._thread.join(timeout=2)
