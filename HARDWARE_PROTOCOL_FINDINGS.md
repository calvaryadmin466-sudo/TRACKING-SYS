# Hardware & Protocol Findings — XV-900-8 / ZH900

This document records what is **established**, what is **assumed**, and what is
**still open** about the target terminal's communication protocol. It is the
source of truth the decoder is built against. Nothing here is invented: every
"established" item is backed by the supplied device manual or the public JT/T
standards, and everything not yet confirmed against a physical device is marked
as such.

Last updated: 2026-11-03 (Stage 1).

---

## 1. Device identification (ESTABLISHED — from the manual)

- The supplied manual is **"User Manual of XV-900-8"** (internally "ZH900 /
  V300 series"), a **vehicle MDVR** (mobile DVR), not a plain GPS tracker.
- **8-channel AHD 1080P** video; **H.264 / H.265** compression; main + sub stream.
- Connectivity: **3G/4G dial + WiFi + SIM**; connects out to a configurable
  server IP/port.
- I/O: **4 alarm inputs, 2 alarm outputs**, **1× RS485**, **1× RS232**.
- Ignition sensed via the **ACC wire** (yellow power lead).
- Alarm sources: I/O, speed/overspeed, acceleration, temperature, voltage, radar,
  plus DMS/ADAS/BSD driver-assist events.

## 2. Protocol selection (ESTABLISHED — from the manual)

The terminal supports two distinct uplink modes, selected in its menu:

1. **"Monitoring platform"** — the manufacturer's proprietary video-server
   protocol (manual: "report the IP address of the video server").
2. **"Ministry standard platform"** — the Chinese national standard. The manual
   is explicit (§6.1.4): *"the ministry protocol must choose 1078."*

**Decision:** this platform targets the **ministry-standard mode**, i.e.
**JT/T 808** for signalling + GPS and **JT/T 1078** for video. This is an open,
documented standard, so the decoder can be written against it without inventing
anything — unlike the proprietary video mode.

## 3. Device identity model (ESTABLISHED — from the manual)

The manual (§5.2.2) states: *"modify the mobile phone number in the terminal
settings (that is the unique ID of the reporting server)."*

- The **reporting ID** is the terminal's **"mobile phone number"** field, encoded
  as JT/T 808 BCD (6 bytes in 2013, 10 bytes in 2019).
- The **hardware serial number** is a **separate** field ("Device number: display
  device serial number").
- The platform therefore stores **three independent identifiers**:
  reporting ID, hardware serial number, internal DB id — never assumed equal.

## 4. JT/T 808 framing (ESTABLISHED — public standard, IMPLEMENTED & TESTED)

Implemented in `services/ingestion/internal/jt808`:

- Frame delimiter `0x7e`; transport escaping `0x7d 0x01 → 0x7d`, `0x7d 0x02 → 0x7e`.
- Header: message id (WORD), body attributes (WORD), optional 1-byte version
  (2019), BCD phone (6/10 bytes), serial (WORD), optional fragmentation (2×WORD).
- Body attributes: bits 0-9 length, 10-12 encryption, 13 fragmentation, 14 version.
- Check code: XOR of header+body.

Verified by Go unit tests **and** an independent Python reference
(`tools/verify_protocol.py`), including the canonical heartbeat check vector
(`checksum == 0xce`).

## 5. Supported messages in Stage 1 (IMPLEMENTED)

| ID       | Direction | Name                         | Status |
|----------|-----------|------------------------------|--------|
| `0x0100` | T → P     | Terminal registration        | Decoded; replies `0x8100` with auth code |
| `0x0102` | T → P     | Terminal authentication      | Decoded; replies `0x8001` success |
| `0x0002` | T → P     | Heartbeat                    | Decoded; replies `0x8001` success |
| `0x0200` | T → P     | Location report              | Decoded (position + status + extras); replies `0x8001` |
| `0x0003` | T → P     | Logout                       | Acknowledged |
| `0x0001` | T → P     | Terminal general response    | Accepted (no reply) |
| `0x8001` | P → T     | Platform general response    | Built by server |
| `0x8100` | P → T     | Registration response        | Built by server |

Every other message id is **recognised as unknown, stored, and acknowledged as
"unsupported" (`0x8001` result 3)** — never silently discarded.

### 0x0200 location decoding (IMPLEMENTED)

Alarm flag (DWORD), status (DWORD), latitude/longitude (DWORD, ÷1e6, signed via
status bits 2/3), altitude (WORD, m), speed (WORD, ÷10 km/h), heading (WORD),
BCD time (6 bytes), then additional-info TLV items. Decoded extras: mileage
(`0x01`), signal strength (`0x30`), satellite count (`0x31`); all other items are
preserved raw. Status bit 0 = ACC/ignition, bit 1 = positioned (used to mark a
fix fresh/valid vs stale).

## 6. ASSUMPTIONS (must be confirmed against a physical XV-900-8)

- **Protocol version in use** (2013 vs 2019 header). The decoder auto-detects via
  the version flag, so both are handled, but which the device actually sends is
  unconfirmed.
- **Registration body field widths**. 2013 (5/20/7) vs 2019 (11/30/30) layouts are
  both implemented and selected by the version flag; the exact manufacturer/model
  strings the XV-900-8 emits are unconfirmed.
- **Transport = TCP**. JT/T 808 runs over TCP or UDP; this server implements TCP,
  which is the common MDVR default. UDP is not yet implemented.
- **License plate encoding** is likely GBK on the device; Stage 1 keeps it as
  best-effort bytes/ASCII. GBK transcoding is a follow-up.
- **Additional-info item set** beyond the three decoded above will vary by
  firmware; unknown items are retained raw for later decoding.

## 7. OPEN QUESTIONS (require device testing or vendor docs)

1. Exact firmware/protocol version string reported by your units.
2. Whether your units use any **vendor-specific message IDs** (0x0900 pass-through,
   proprietary alarms). The raw-packet store will reveal these on first contact.
3. **JT/T 1078 video**: stream establishment, real-time audio/video control
   (`0x9101`/`0x9102`), file list and playback commands — deferred to the media
   gateway service (Stage 4) and must be validated against the device.
4. Whether the device requires a specific **registration pre-provisioning** on the
   platform side (some platforms reject unknown terminals). Stage 1 accepts and
   records any terminal; tighten to a provisioning allowlist before production.
5. Authentication semantics: the server issues an auth code on registration and
   accepts the device's `0x0102`; confirm the device re-uses a persisted auth code
   across reconnects as expected.

## 8. How these findings were validated

- Manual text extracted and read (networking, platform, identity, camera sections).
- JT/T 808 framing/decoding implemented from the public standard and checked with
  Go unit tests + the Python cross-check.
- **Not yet validated against a physical XV-900-8** — see `README.md` →
  "Pointing a real device at the server" for the exact steps to do so, and watch
  the `raw_packets` table / server logs for the first real frames.
