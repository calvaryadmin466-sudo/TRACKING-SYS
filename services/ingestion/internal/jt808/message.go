package jt808

import (
	"encoding/binary"
	"fmt"
)

// Message IDs used by the XV-900-8 in JT/T 808 ministry mode. Only the IDs this
// server actually understands are decoded; every other ID is reported as an
// unknown message so it can be logged and acknowledged rather than discarded.
const (
	MsgTerminalGeneralResp uint16 = 0x0001 // terminal -> platform, generic ack
	MsgTerminalHeartbeat   uint16 = 0x0002 // terminal -> platform, keepalive
	MsgTerminalLogout      uint16 = 0x0003 // terminal -> platform, logout
	MsgTerminalRegister    uint16 = 0x0100 // terminal -> platform, registration
	MsgTerminalAuth        uint16 = 0x0102 // terminal -> platform, authentication
	MsgLocationReport      uint16 = 0x0200 // terminal -> platform, position
	MsgLocationBatch       uint16 = 0x0704 // terminal -> platform, batch positions

	MsgPlatformGeneralResp uint16 = 0x8001 // platform -> terminal, generic ack
	MsgRegisterResp        uint16 = 0x8100 // platform -> terminal, registration ack
	MsgTextMessage         uint16 = 0x8300 // platform -> terminal, text message distribution
)

// messageNames maps known message IDs to a human label for logs and diagnostics.
var messageNames = map[uint16]string{
	MsgTerminalGeneralResp: "terminal_general_response",
	MsgTerminalHeartbeat:   "terminal_heartbeat",
	MsgTerminalLogout:      "terminal_logout",
	MsgTerminalRegister:    "terminal_register",
	MsgTerminalAuth:        "terminal_auth",
	MsgLocationReport:      "location_report",
	MsgLocationBatch:       "location_batch",
	MsgPlatformGeneralResp: "platform_general_response",
	MsgRegisterResp:        "register_response",
	MsgTextMessage:         "text_message",
}

// MessageName returns a human-readable name for a message ID, or a hex fallback.
func MessageName(id uint16) string {
	if n, ok := messageNames[id]; ok {
		return n
	}
	return fmt.Sprintf("unknown_0x%04x", id)
}

// Platform general response result codes (body of 0x8001).
const (
	ResultSuccess      byte = 0x00
	ResultFailure      byte = 0x01
	ResultMessageError byte = 0x02
	ResultUnsupported  byte = 0x03
	ResultAlarmAck     byte = 0x04
)

// Registration response result codes (body of 0x8100).
const (
	RegResultSuccess           byte = 0x00
	RegResultVehicleRegistered byte = 0x01
	RegResultNoSuchVehicle     byte = 0x02
	RegResultTerminalReged     byte = 0x03
	RegResultNoSuchTerminal    byte = 0x04
)

func be16(b []byte) uint16 { return binary.BigEndian.Uint16(b) }
func be32(b []byte) uint32 { return binary.BigEndian.Uint32(b) }
