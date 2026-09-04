"""Named sessions, connection health, and the registry.

Shows the distinction the package insists on: a transport can be open while the
instrument is not answering.

    python examples/02_sessions_and_health.py
"""

from __future__ import annotations

from scpi_driver_core import ScpiClient, ScpiSession, SessionRegistry
from scpi_driver_core.exceptions import IdentityError, TransportError
from scpi_driver_core.models import Identity
from scpi_driver_core.simulation import ScriptedScpiTransport


def build(alias: str, model: str) -> ScpiSession:
    instrument = ScriptedScpiTransport()
    instrument.on("*IDN?", f"ACME,{model},SN{alias.upper()},1.0")
    return ScpiSession(alias, ScpiClient(instrument))


def require_acme(identity: Identity) -> None:
    """A concrete driver decides what it will talk to. The core never does."""
    if identity.manufacturer != "ACME":
        raise IdentityError(f"expected an ACME instrument, found {identity.manufacturer}")


def main() -> None:
    registry = SessionRegistry()
    for alias, model in (("psu", "PSU-1000"), ("dmm", "DMM-2000")):
        session = build(alias, model)
        session.open(probe=True, validate_identity=require_acme)
        registry.register(alias, session)

    print("aliases       :", registry.list_aliases())
    print("active        :", registry.active_alias)

    registry.set_active("dmm")
    active = registry.get_active()
    print("active model  :", active.get_identity().model)
    print("generation    :", active.generation)

    # An open transport is not a promise that the instrument replies.
    psu = registry.get("psu")
    psu.transport.inner.fail_next_read(TransportError("instrument powered down"), fault=False)
    print("psu connected :", psu.is_connected)
    print("psu answering :", psu.check_communication())
    print("psu health    :", psu.health.communication_ok, "-", psu.health.last_error)

    registry.disconnect_all()
    print("after cleanup :", registry.list_aliases())


if __name__ == "__main__":
    main()
