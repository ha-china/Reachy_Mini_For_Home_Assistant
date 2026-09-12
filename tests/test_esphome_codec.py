"""Tests for the ESPHome wire codec (frame encode/decode)."""

import pytest
from aioesphomeapi.api_pb2 import HelloRequest, PingRequest

from reachy_mini_home_assistant.protocol.esphome_codec import (
    MESSAGE_TYPE_TO_PROTO,
    decode_frame_stream,
    encode_frame,
    encode_packets,
    encode_varuint,
)


class TestVaruint:
    def test_single_byte_values(self):
        assert encode_varuint(0) == b"\x00"
        assert encode_varuint(0x7F) == b"\x7f"

    def test_multi_byte_values(self):
        assert encode_varuint(128) == b"\x80\x01"
        assert encode_varuint(300) == b"\xac\x02"

    def test_large_value(self):
        assert encode_varuint(2**28) == b"\x80\x80\x80\x80\x01"


class TestEncodeFrame:
    def test_empty_payload(self):
        # preamble | length=0 | msg_type
        assert encode_frame(1, b"") == b"\x00\x00\x01"

    def test_known_frame(self):
        payload = PingRequest().SerializeToString()
        frame = encode_frame(61, payload)
        assert frame[0] == 0x00
        assert frame[1] == len(payload)
        assert frame[2] == 61
        assert frame[3:] == payload


class TestEncodeDecodeRoundTrip:
    def test_round_trip_multiple_packets(self):
        packets = [
            (1, HelloRequest().SerializeToString()),
            (61, b"\x01\x02\x03"),
            (1, b""),
        ]
        wire = encode_packets(packets)
        assert decode_frame_stream(wire) == packets

    def test_large_payload_varint_length(self):
        payload = b"x" * 500  # length 500 needs a multi-byte varuint
        wire = encode_frame(2, payload)
        assert decode_frame_stream(wire) == [(2, payload)]

    def test_decode_rejects_bad_preamble(self):
        with pytest.raises(ValueError, match="bad preamble"):
            decode_frame_stream(b"\x01\x01\x01")

    def test_decode_rejects_truncation(self):
        with pytest.raises(ValueError, match="truncated"):
            decode_frame_stream(b"\x00\x10\x01abc")  # length 16, only 3 bytes


class TestMessageMap:
    def test_known_types_present(self):
        assert MESSAGE_TYPE_TO_PROTO[1].__name__ == "HelloRequest"
        assert MESSAGE_TYPE_TO_PROTO[2].__name__ == "HelloResponse"

    def test_map_covers_protocol_v1_10(self):
        # The map must cover everything HA may send us; 1.10 protocol has ~150 types
        assert len(MESSAGE_TYPE_TO_PROTO) >= 140
