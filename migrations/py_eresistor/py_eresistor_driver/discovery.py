"""Network discovery helpers for E-Resistor boards."""
from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from .http_api import EResistorHttpApi
from .models import BoardInfo
from .scpi import ScpiTransport
from .validation import parse_idn


def _probe_host(host: str, *, scpi_port: int, http_port: int, timeout: float) -> BoardInfo | None:
    http_ok = False
    scpi_ok = False
    idn: str | None = None
    serial: str | None = None
    firmware: str | None = None

    http = EResistorHttpApi(host, http_port, timeout=timeout)
    http_ok = http.ping()

    scpi = ScpiTransport(host, scpi_port, timeout=timeout, retries=0, read_greeting=True)
    try:
        scpi.connect()
        idn = scpi.request("*IDN?")
        scpi_ok = True
        serial, firmware = parse_idn(idn)
    except Exception:
        scpi_ok = False
    finally:
        scpi.close()

    if idn and "OPENBENCH" in idn.upper() and "E-RESISTOR" in idn.upper():
        return BoardInfo(host=host, serial=serial, firmware_version=firmware, idn=idn, http_ok=http_ok, scpi_ok=scpi_ok)
    if http_ok and scpi_ok:
        return BoardInfo(host=host, serial=serial, firmware_version=firmware, idn=idn, http_ok=http_ok, scpi_ok=scpi_ok)
    return None


def discover_boards(
    subnet: str,
    *,
    scpi_port: int = 5025,
    http_port: int = 80,
    timeout: float = 0.25,
    max_workers: int = 64,
) -> list[BoardInfo]:
    network = ipaddress.ip_network(subnet, strict=False)
    hosts = [str(ip) for ip in network.hosts()]
    boards: list[BoardInfo] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_probe_host, host, scpi_port=scpi_port, http_port=http_port, timeout=timeout): host for host in hosts}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                boards.append(result)
    return sorted(boards, key=lambda b: tuple(int(p) for p in b.host.split(".")))


def _local_ipv4_candidates() -> list[str]:
    candidates: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            candidates.add(info[4][0])
    except OSError:
        pass
    # UDP trick: no packets need to be delivered, but the OS chooses the outbound interface.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            candidates.add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    return sorted(ip for ip in candidates if not ip.startswith("127."))


def discover_boards_auto(*, timeout: float = 0.25, max_workers: int = 64) -> list[BoardInfo]:
    boards: list[BoardInfo] = []
    seen: set[str] = set()
    for ip in _local_ipv4_candidates():
        parts = ip.split(".")
        if len(parts) != 4:
            continue
        subnet = ".".join(parts[:3]) + ".0/24"
        for board in discover_boards(subnet, timeout=timeout, max_workers=max_workers):
            if board.host not in seen:
                boards.append(board)
                seen.add(board.host)
    return boards
