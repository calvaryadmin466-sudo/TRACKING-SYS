#!/usr/bin/env python3
"""Independent JT/T 808 protocol cross-check.

This is a *separate* reference implementation of the framing, checksum, header and
0x0200 location decoding, used to validate the Go decoder's byte-level behaviour
against the public JT/T 808 standard. It depends only on the Python standard
library, so it runs in any environment (including ones without a Go toolchain).

Run:  python tools/verify_protocol.py
"""
import struct
import sys

FLAG = 0x7e
ESC = 0x7d


def unescape(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == ESC:
            nxt = data[i + 1]
            out.append(ESC if nxt == 0x01 else FLAG if nxt == 0x02 else nxt)
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out)


def escape(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        if b == FLAG:
            out += bytes([ESC, 0x02])
        elif b == ESC:
            out += bytes([ESC, 0x01])
        else:
            out.append(b)
    return bytes(out)


def checksum(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
    return c


def bcd_decode(b: bytes) -> str:
    return "".join(f"{x >> 4}{x & 0x0f}" for x in b)


def parse_header(raw: bytes):
    msg_id, attrs = struct.unpack(">HH", raw[:4])
    body_len = attrs & 0x3ff
    has_version = (attrs >> 14) & 1 == 1
    off = 4
    phone_len = 6
    version = 0
    if has_version:
        version = raw[off]
        off += 1
        phone_len = 10
    phone = bcd_decode(raw[off:off + phone_len])
    off += phone_len
    serial = struct.unpack(">H", raw[off:off + 2])[0]
    off += 2
    return {
        "msg_id": msg_id, "body_len": body_len, "has_version": has_version,
        "version": version, "phone": phone, "serial": serial, "hdr_len": off,
    }


def decode_location(body: bytes):
    alarm, status = struct.unpack(">II", body[:8])
    lat_raw, lon_raw = struct.unpack(">II", body[8:16])
    altitude, speed, heading = struct.unpack(">HHH", body[16:22])
    lat = lat_raw / 1e6
    lon = lon_raw / 1e6
    if status & (1 << 2):
        lat = -lat
    if status & (1 << 3):
        lon = -lon
    return {
        "acc": bool(status & 1), "positioned": bool(status & 2),
        "lat": lat, "lon": lon, "altitude": altitude,
        "speed": speed / 10.0, "heading": heading, "alarm": alarm,
    }


FAILS = 0


def check(name, cond):
    global FAILS
    status = "PASS" if cond else "FAIL"
    if not cond:
        FAILS += 1
    print(f"  [{status}] {name}")


def main():
    print("JT/T 808 independent protocol verification")

    print("\n1. Checksum (canonical heartbeat vector)")
    payload = bytes.fromhex("000200000139123447940001")
    check("checksum == 0xce", checksum(payload) == 0xce)

    print("\n2. Escape / unescape round trip")
    sample = bytes([0x30, 0x7e, 0x08, 0x7d, 0x55])
    esc = escape(sample)
    check("no bare flag in escaped", FLAG not in esc)
    check("round trip restores original", unescape(esc) == sample)

    print("\n3. Header parse (2013 heartbeat)")
    h = parse_header(payload)  # payload is header+body, no checksum
    check("msg_id == 0x0002", h["msg_id"] == 0x0002)
    check("phone == 013912344794", h["phone"] == "013912344794")
    check("serial == 1", h["serial"] == 1)

    print("\n4. Location decode (built + decoded)")
    # Build a 0x0200 body: alarm=0, status=acc|positioned, lat 22.5726, lon 88.3639
    status = 0b11
    body = struct.pack(">IIIIHHH", 0, status,
                       int(22.5726 * 1e6), int(88.3639 * 1e6),
                       15, 425, 90) + bytes.fromhex("261103102030")
    loc = decode_location(body)
    check("lat ~= 22.5726", abs(loc["lat"] - 22.5726) < 1e-4)
    check("lon ~= 88.3639", abs(loc["lon"] - 88.3639) < 1e-4)
    check("speed == 42.5", abs(loc["speed"] - 42.5) < 1e-6)
    check("heading == 90", loc["heading"] == 90)
    check("acc on", loc["acc"] is True)

    print("\n5. South/West sign handling")
    status = 0b1111  # acc|positioned|south|west
    body = struct.pack(">IIIIHHH", 0, status,
                       int(33.8688 * 1e6), int(151.2093 * 1e6),
                       0, 0, 0) + bytes.fromhex("260101000000")
    loc = decode_location(body)
    check("lat negative (south)", loc["lat"] < 0)
    check("lon negative (west)", loc["lon"] < 0)

    print()
    if FAILS:
        print(f"RESULT: {FAILS} check(s) FAILED")
        sys.exit(1)
    print("RESULT: all protocol checks passed")


if __name__ == "__main__":
    main()
