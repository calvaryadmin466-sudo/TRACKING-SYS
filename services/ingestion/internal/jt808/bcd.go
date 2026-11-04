package jt808

import (
	"errors"
	"strings"
)

// ErrBadBCD indicates a non-decimal nibble in a BCD field.
var ErrBadBCD = errors.New("jt808: invalid BCD digit")

// decodeBCD converts BCD-encoded bytes into their decimal digit string. Each
// byte holds two digits (high nibble first). Invalid nibbles yield ErrBadBCD.
func decodeBCD(b []byte) (string, error) {
	var sb strings.Builder
	for _, x := range b {
		hi := x >> 4
		lo := x & 0x0f
		if hi > 9 || lo > 9 {
			return "", ErrBadBCD
		}
		sb.WriteByte('0' + hi)
		sb.WriteByte('0' + lo)
	}
	return sb.String(), nil
}

// encodeBCD encodes a decimal digit string into n BCD bytes, left-padding with
// zeros so the result is exactly n bytes (2n digits). Extra leading digits are
// truncated from the left to fit, matching how terminals store the phone field.
func encodeBCD(digits string, n int) []byte {
	want := n * 2
	if len(digits) < want {
		digits = strings.Repeat("0", want-len(digits)) + digits
	} else if len(digits) > want {
		digits = digits[len(digits)-want:]
	}
	out := make([]byte, n)
	for i := 0; i < n; i++ {
		hi := digits[i*2] - '0'
		lo := digits[i*2+1] - '0'
		out[i] = (hi << 4) | lo
	}
	return out
}

// normalizePhone trims leading zeros from a decoded BCD phone string to produce
// the canonical device reporting ID, keeping "0" if every digit was zero.
func normalizePhone(digits string) string {
	trimmed := strings.TrimLeft(digits, "0")
	if trimmed == "" {
		return "0"
	}
	return trimmed
}
