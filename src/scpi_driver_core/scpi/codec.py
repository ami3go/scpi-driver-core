"""SCPI text framing, layered above the byte transport.

The codec owns exactly one job: turning a command string into the bytes that go
on the wire, and turning response bytes back into a string. It is the only
place allowed to add or remove framing, and it removes only the terminator it
was configured with. Generic ``strip()``/``rstrip()`` is never used, because
trailing whitespace and null bytes can be payload.

Binary transfers bypass this layer entirely; see
:mod:`scpi_driver_core.scpi.binary_block`.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ProtocolError,
    ResponseParseError,
)

__all__ = ["ScpiTextCodec"]


@dataclass(frozen=True)
class ScpiTextCodec:
    """Encodes SCPI commands and decodes SCPI responses.

    Args:
        encoding: text encoding, stated explicitly rather than assumed.
        command_terminator: appended to outbound commands. Use ``b""`` for a
            backend that frames messages itself, such as VISA.
        response_terminator: removed from the end of a response when present.
            ``None`` means responses are not terminated.
        decode_errors: passed to the decoder; strict by default, so a malformed
            response is reported rather than silently mangled.
        maximum_command_size: largest encoded command permitted, terminator
            included.
        maximum_response_size: largest response accepted.

    Raises:
        ConfigurationError: if the encoding is unknown or a size limit is not
            positive.
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

    def encode_command(self, command: str) -> bytes:
        """Encode ``command`` and terminate it exactly once.

        A command that already ends with the configured terminator is not
        terminated again, so callers that write their own terminator do not
        produce a doubled one.

        Raises:
            ConfigurationError: if the command cannot be encoded, or exceeds
                ``maximum_command_size``.
        """
        try:
            encoded = command.encode(self.encoding, errors="strict")
        except UnicodeEncodeError as exc:
            raise ConfigurationError(
                f"command is not encodable as {self.encoding}: {command!r}"
            ) from exc

        if self.command_terminator and not encoded.endswith(self.command_terminator):
            encoded += self.command_terminator

        if len(encoded) > self.maximum_command_size:
            raise ConfigurationError(
                f"command of {len(encoded)} bytes exceeds "
                f"maximum_command_size {self.maximum_command_size}"
            )
        return encoded

    def encode_block_command(self, prefix: str, block: bytes) -> bytes:
        """Frame a text prefix followed by raw binary, as ``CURV #41234...\\n``.

        The terminator is appended unconditionally, unlike
        :meth:`encode_command`. A binary block can legitimately end with the
        same byte as the terminator, so testing for one already present would
        occasionally drop it and leave the instrument waiting.

        ``maximum_command_size`` bounds only the text prefix here. It exists to
        catch runaway command construction, whereas the size of a waveform or
        setup upload is a deliberate choice by the caller and is limited by the
        instrument itself.

        Raises:
            ConfigurationError: if the prefix cannot be encoded or exceeds
                ``maximum_command_size``.
        """
        try:
            encoded = prefix.encode(self.encoding, errors="strict")
        except UnicodeEncodeError as exc:
            raise ConfigurationError(
                f"command prefix is not encodable as {self.encoding}: {prefix!r}"
            ) from exc
        if len(encoded) > self.maximum_command_size:
            raise ConfigurationError(
                f"command prefix of {len(encoded)} bytes exceeds "
                f"maximum_command_size {self.maximum_command_size}"
            )
        return encoded + block + self.command_terminator

    def decode_response(self, data: bytes) -> str:
        """Remove one trailing terminator if present, then decode.

        Only the exact configured terminator is removed, and only from the end.
        Everything else, including interior and trailing whitespace, is
        preserved for the parsers to deal with.

        Raises:
            ProtocolError: if the response exceeds ``maximum_response_size``.
            ResponseParseError: if the bytes are not decodable.
        """
        if len(data) > self.maximum_response_size:
            raise ProtocolError(
                f"response of {len(data)} bytes exceeds "
                f"maximum_response_size {self.maximum_response_size}"
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
