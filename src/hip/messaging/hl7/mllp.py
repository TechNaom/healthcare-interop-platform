"""MLLP framing — the Minimal Lower Layer Protocol wrapper for HL7 v2 over TCP.

MLLP frames a message as ``<VT> message <FS><CR>`` (docs/TECH_STACK.md — simple
enough that a dedicated dependency isn't warranted). This module owns the byte
framing only; parsing is ``parser`` and the socket server is ``listener``.
"""

from __future__ import annotations

from collections.abc import Iterator

# MLLP control bytes.
VT = 0x0B  # <VT> start-of-block
FS = 0x1C  # <FS> end-of-block
CR = 0x0D  # <CR> carriage return (follows FS)

_START = bytes([VT])
_END = bytes([FS, CR])


def wrap(message: str, encoding: str = "utf-8") -> bytes:
    """Frame an HL7 message string for transmission over MLLP."""
    return _START + message.encode(encoding) + _END


class MLLPBuffer:
    """Reassembles a byte stream into complete MLLP-framed messages.

    TCP is a stream, not a message boundary — a single ``recv`` may contain part
    of a message, several messages, or a split frame. Feed bytes in; take fully
    framed messages out. Anything after the last complete frame is retained for
    the next feed.
    """

    def __init__(self, encoding: str = "utf-8") -> None:
        self._buf = bytearray()
        self._encoding = encoding

    def feed(self, data: bytes) -> Iterator[str]:
        """Append bytes and yield each complete message (unframed, decoded)."""
        self._buf.extend(data)
        while True:
            start = self._buf.find(VT)
            if start == -1:
                # No start byte yet; drop leading noise to avoid unbounded growth.
                self._buf.clear()
                return
            end = self._buf.find(FS, start + 1)
            if end == -1:
                # Incomplete frame; keep from the start byte and wait for more.
                del self._buf[:start]
                return
            payload = bytes(self._buf[start + 1 : end])
            # Consume through the FS and its trailing CR if present.
            consumed = end + 1
            if consumed < len(self._buf) and self._buf[consumed] == CR:
                consumed += 1
            del self._buf[:consumed]
            yield payload.decode(self._encoding)
