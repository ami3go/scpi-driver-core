from __future__ import annotations

import threading

import pytest

from scpi_driver_core import ScpiClient, ScpiSession
from scpi_driver_core.simulation import ScriptedScpiTransport

pytestmark = [pytest.mark.integration, pytest.mark.watchdog]


@pytest.mark.timeout(5)
def test_concurrent_session_queries_finish_without_deadlock() -> None:
    transport = ScriptedScpiTransport().on(
        "*IDN?", "SCPI Core,Concurrency Simulator,SIM-LOCK,1.0"
    )
    session = ScpiSession("concurrency", ScpiClient(transport))
    session.open()

    worker_count = 8
    iterations = 20
    start = threading.Barrier(worker_count)
    errors: list[BaseException] = []
    error_lock = threading.Lock()

    def worker(worker_id: int) -> None:
        try:
            start.wait(timeout=1.0)
            for iteration in range(iterations):
                if (worker_id + iteration) % 2:
                    assert session.get_identity(refresh=True).model == "Concurrency Simulator"
                else:
                    assert session.check_communication() is True
        except BaseException as exc:  # noqa: BLE001 - thread failures are reported below
            with error_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(worker_count)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)

        assert not [thread for thread in threads if thread.is_alive()]
        assert not errors
        assert len(transport.history) == worker_count * iterations
    finally:
        session.close()
