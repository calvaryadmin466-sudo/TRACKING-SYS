#!/usr/bin/env python3
"""Independent JT/T 1078 packet-format cross-check.

A separate reference implementation of the JT/T 1078-2016 "01cd" packet framing,
used to validate the Go `internal/jt1078` parser's byte-level behaviour (header
lengths per data type, field offsets, body handling) without needing a Go
toolchain. Standard library only.

Run:  python tools/verify_jt1078.py
"""
import struct
import sys

MAGIC = bytes([0x30, 0x31, 0x63, 0x64])
DATA_VIDEO_I, DATA_VIDEO_P, DATA_AUDIO, DATA_TRANSPARENT = 0x0, 0x1, 0x3, 0x4
FAILS = 0


def check(name, cond):
    global FAILS
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILS += 1


def bcd6(digits: str) -> bytes:
    digits = digits.zfill(12)[-12:]
    return bytes((int(digits[i * 2]) << 4) | int(digits[i * 2 + 1]) for i in range(6))


def build(sim, channel, data_type, body, seq=1, pt=98, ts=1699000000000, mark=True):
    out = bytearray(MAGIC)
    out.append(0x81)
    out.append((0x80 if mark else 0) | (pt & 0x7f))
    out += struct.pack(">H", seq)
    out += bcd6(sim)
    out.append(channel)
    out.append((data_type << 4) | 0)
    if data_type != DATA_TRANSPARENT:
        out += struct.pack(">Q", ts)
    if data_type in (DATA_VIDEO_I, DATA_VIDEO_P):
        out += struct.pack(">HH", 40, 40)
    out += struct.pack(">H", len(body))
    out += body
    return bytes(out)


def header_len(data_type):
    return {DATA_AUDIO: 26, DATA_TRANSPARENT: 18}.get(data_type, 30)


def parse(buf):
    assert buf[:4] == MAGIC, "magic"
    pt = buf[5] & 0x7f
    seq = struct.unpack(">H", buf[6:8])[0]
    sim = "".join(f"{b >> 4}{b & 0xf}" for b in buf[8:14]).lstrip("0") or "0"
    channel = buf[14]
    data_type = buf[15] >> 4
    hlen = header_len(data_type)
    off = 16
    ts = None
    if data_type != DATA_TRANSPARENT:
        ts = struct.unpack(">Q", buf[off:off + 8])[0]
        off += 8
    if data_type in (DATA_VIDEO_I, DATA_VIDEO_P):
        off += 4
    body_len = struct.unpack(">H", buf[off:off + 2])[0]
    off += 2
    body = buf[off:off + body_len]
    return {"pt": pt, "seq": seq, "sim": sim, "channel": channel, "data_type": data_type,
            "ts": ts, "header_len": off, "body": body, "total": off + body_len}, hlen


def main():
    print("JT/T 1078 independent packet-format verification")

    print("\n1. Video I-frame round trip")
    raw = build("100000000001", 1, DATA_VIDEO_I, b"\x00\x00\x00\x01\x67", seq=7)
    p, hlen = parse(raw)
    check("header length == 30", p["header_len"] == 30 == hlen)
    check("sim == 100000000001", p["sim"] == "100000000001")
    check("channel == 1", p["channel"] == 1)
    check("seq == 7", p["seq"] == 7)
    check("body preserved", p["body"] == b"\x00\x00\x00\x01\x67")
    check("total == len(raw)", p["total"] == len(raw))

    print("\n2. Audio header length == 26")
    p, _ = parse(build("1", 2, DATA_AUDIO, b"\x01\x02\x03"))
    check("audio header 26", p["header_len"] == 26)

    print("\n3. Transparent header length == 18 (no timestamp)")
    p, _ = parse(build("1", 3, DATA_TRANSPARENT, b"\x09"))
    check("transparent header 18", p["header_len"] == 18)
    check("no timestamp", p["ts"] is None)

    print("\n4. Concatenated packets are individually framed")
    stream = build("1", 1, DATA_VIDEO_I, b"ab") + build("1", 1, DATA_VIDEO_P, b"cde")
    p1, _ = parse(stream)
    p2, _ = parse(stream[p1["total"]:])
    check("first body 'ab'", p1["body"] == b"ab")
    check("second body 'cde'", p2["body"] == b"cde")

    print()
    if FAILS:
        print(f"RESULT: {FAILS} check(s) FAILED")
        sys.exit(1)
    print("RESULT: all JT/T 1078 format checks passed")


if __name__ == "__main__":
    main()
