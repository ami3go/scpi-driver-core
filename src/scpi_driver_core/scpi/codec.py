"""SCPI text framing, layered above the byte transport.

Binary transfers bypass this layer entirely. Text commands are one program
message each: embedded CR/LF is rejected rather than allowed to inject a second
instrument command.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass

from scpi_driver_core.exceptions import ConfigurationError, ProtocolError, ResponseParseError

__all__ = ["ScpiTextCodec"]


@dataclass(frozen=True)
class ScpiTextCodec:
    """Encodes SCPI text while preserving byte-level framing explicitly.

    ``command_terminator=b""`` is appropriate only when the selected transport
    guarantees message framing for writes. It must not be assumed for VISA
    ASRL or TCPIP::SOCKET resources merely because VISA is in use.
    """

    encoding: str = "ascii"
    command_terminator: bytes = b"\n"
    response_terminator: bytes | None = b"\n"
    decode_errors: str = "strict"
    maximum_command_size: int = 65_536
    maximum_response_size: int = 1_048_576

    def __post_init__(self) -> None:
        try:
            codecs.lookup(self.encoding)
        except LookupError as exc:
            raise ConfigurationError(f"unknown encoding {self.encoding!r}") from exc
        if self.maximum_command_size <= 0:
            raise ConfigurationError(
                f"maximum_command_size must be positive, got {self.maximum_command_size}"
            )
        if self.maximum_response_size <= 0:
            raise ConfigurationError(
                f"maximum_response_size must be positive, got {self.maximum_response_size}"
            )
        if b"\r" in self.command_terminator or b"\n" in self.command_terminator:
            return
        if self.command_terminator and any(
            token in self.command_terminator for token in (b"\r", b"\n")
        ):
            raise ConfigurationError("command terminator must be a valid byte sequence")

    def encode_command(self, command: str) -> bytes:
        """Encode one command and terminate it exactly once.

        A single already-present trailing terminator is accepted. Any CR/LF or
        configured terminator remaining inside the body is rejected.
        """
        try:
            body = command.encode(self.encoding, errors="strict")
        except UnicodeEncodeError as exc:
            raise ConfigurationError(
                f"command is not encodable as {self.encoding}: {command!r}"
            ) from exc

        terminator = self.command_terminator
        if terminator and body.endswith(terminator):
            body = body[: -len(terminator)]

        forbidden = [b"\r", b"\n"]
        if terminator and terminator not in forbidden:
            forbidden.append(terminator)
        if any(token and token in body for token in forbidden):
            raise ConfigurationError(
                f"command contains an embedded line break or terminator: {command!r}; "
                "send separate commands, or use write_bytes() deliberately"
            )

        encoded = body + terminator
        if len(encoded) > self.maximum_command_size:
            raise ConfigurationError(
                f"command of {len(encoded)} bytes exceeds maximum_command_size "
                f"{self.maximum_command_size}"
            )
        return encoded

    def encode_block_command(self, prefix: str, block: bytes) -> bytes:
        """Frame a text prefix followed by an arbitrary binary block."""
        if "\r" in prefix or "\n" in prefix:
            raise ConfigurationError("binary-block command prefix must not contain CR or LF")
        try:
            encoded = prefix.encode(self.encoding, errors="strict")
        except UnicodeEncodeError as exc:
            raise ConfigurationError(
                f"command prefix is not encodable as {self.encoding}: {prefix!r}"
            ) from exc
        if len(encoded) > self.maximum_command_size:
            raise ConfigurationError(
                f"command prefix of {len(encoded)} bytes exceeds maximum_command_size "
                f"{self.maximum_command_size}"
            )
        return encoded + block + self.command_terminator

    def decode_response(self, data: bytes) -> str:
        """Remove one exact trailing response terminator, then decode."""
        if len(data) > self.maximum_response_size:
            raise ProtocolError(
                f"response of {len(data)} bytes exceeds maximum_response_size "
                f"{self.maximum_response_size}"
            )
        payload = data
        terminator = self.response_terminator
        if terminator and payload.endswith(terminator):
            payload = payload[: -len(terminator)]
        try:
            return payload.decode(self.encoding, errors=self.decode_errors)
        except UnicodeDecodeError as exc:
            raise ResponseParseError(
                f"response is not decodable as {self.encoding}", raw=data
            ) from exc
