"""ESPHome API wire codec for our server-side connection.

The frame format is the stable ESPHome plaintext protocol:
``0x00 preamble | varuint length | varuint message_type | protobuf payload``.

We own this encoding because aioesphomeapi's ``make_plain_text_packets`` lives
in a private module (``_frame_helper``) that changes between releases; ours is
byte-identical and covered by unit tests. The message-number mapping is taken
from ``aioesphomeapi.core`` (public, stable).
"""

from __future__ import annotations

from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO

__all__ = [
    "MESSAGE_TYPE_TO_PROTO",
    "decode_frame_stream",
    "encode_frame",
    "encode_packets",
    "encode_varuint",
]

_PREAMBLE = 0x00


def encode_varuint(value: int) -> bytes:
    """Encode an unsigned integer as an ESPHome varuint (LEB128)."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def encode_frame(msg_type: int, payload: bytes) -> bytes:
    """Encode one plaintext ESPHome frame."""
    return bytes([_PREAMBLE]) + encode_varuint(len(payload)) + encode_varuint(msg_type) + payload


def encode_packets(packets: list[tuple[int, bytes]]) -> bytes:
    """Encode consecutive frames for the given (msg_type, payload) packets."""
    return b"".join(encode_frame(t, d) for t, d in packets)


def decode_frame_stream(data: bytes) -> list[tuple[int, bytes]]:
    """Decode a complete byte stream into (msg_type, payload) frames.

    Used by tests and by tools that need to inspect our wire output; the
    server itself parses incrementally in ``APIServer.data_received``.
    """
    frames: list[tuple[int, bytes]] = []
    pos = 0
    size = len(data)

    def _varint(pos: int) -> tuple[int, int]:
        result = 0
        shift = 0
        while True:
            if pos >= size:
                raise ValueError("truncated varint")
            byte = data[pos]
            pos += 1
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return result, pos
            shift += 7

    while pos < size:
        preamble, pos = _varint(pos)
        if preamble != _PREAMBLE:
            raise ValueError(f"bad preamble 0x{preamble:02x} at byte {pos - 1}")
        length, pos = _varint(pos)
        msg_type, pos = _varint(pos)
        if pos + length > size:
            raise ValueError("truncated payload")
        frames.append((msg_type, data[pos : pos + length]))
        pos += length
    return frames
