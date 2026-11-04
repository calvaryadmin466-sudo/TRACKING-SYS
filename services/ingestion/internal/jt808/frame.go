// Package jt808 implements framing and message decoding for the JT/T 808
// vehicle terminal communication protocol as spoken by the XV-900-8 / ZH900
// series MDVR in "ministry standard platform" mode.
//
// The implementation follows the public JT/T 808-2013 / JT/T 808-2019
// standards. Where the two versions differ (header shape, BCD phone length,
// registration body layout) the version flag in the message body attributes
// selects the layout. Nothing here is invented: unrecognised messages are
// surfaced to the caller as "unknown", never silently guessed or discarded.
package jt808

import "errors"

// Flag is the start/end delimiter byte of every JT/T 808 message (0x7e).
const Flag byte = 0x7e

// escape is the escape byte used inside a message body (0x7d).
const escape byte = 0x7d

var (
	// ErrShortFrame is returned when a frame is too short to contain a header.
	ErrShortFrame = errors.New("jt808: frame too short")
	// ErrBadEscape is returned when an escape sequence is malformed.
	ErrBadEscape = errors.New("jt808: invalid escape sequence")
)

// Unescape reverses JT/T 808 transport escaping on the bytes found between two
// delimiter flags. Rules: 0x7d 0x01 -> 0x7d and 0x7d 0x02 -> 0x7e.
func Unescape(in []byte) ([]byte, error) {
	out := make([]byte, 0, len(in))
	for i := 0; i < len(in); i++ {
		b := in[i]
		if b != escape {
			out = append(out, b)
			continue
		}
		if i+1 >= len(in) {
			return nil, ErrBadEscape
		}
		switch in[i+1] {
		case 0x01:
			out = append(out, escape)
		case 0x02:
			out = append(out, Flag)
		default:
			return nil, ErrBadEscape
		}
		i++
	}
	return out, nil
}

// Escape applies JT/T 808 transport escaping. It is the inverse of Unescape and
// is used when building outbound frames: 0x7e -> 0x7d 0x02 and 0x7d -> 0x7d 0x01.
func Escape(in []byte) []byte {
	out := make([]byte, 0, len(in)+8)
	for _, b := range in {
		switch b {
		case Flag:
			out = append(out, escape, 0x02)
		case escape:
			out = append(out, escape, 0x01)
		default:
			out = append(out, b)
		}
	}
	return out
}

// Checksum computes the JT/T 808 check code: the XOR of every byte from the
// start of the message header through the end of the message body (i.e. every
// unescaped byte between the flags except the check code itself).
func Checksum(in []byte) byte {
	var c byte
	for _, b := range in {
		c ^= b
	}
	return c
}

// ExtractFrames scans a stream buffer and returns every complete frame found
// (the escaped bytes between a pair of 0x7e flags, flags removed) together with
// any trailing bytes that do not yet form a complete frame.
//
// It tolerates the two real-world stream shapes:
//   - one flag per boundary:  7e A 7e   7e B 7e
//   - a shared boundary flag: 7e A 7e B 7e
//
// and it handles partial TCP frames (incomplete tail kept in rest) and multiple
// frames arriving in a single read. Leading junk before the first flag is
// dropped by the caller's inspector only after being logged; here it is simply
// skipped so decoding can proceed.
func ExtractFrames(buf []byte) (frames [][]byte, rest []byte) {
	n := len(buf)
	i := 0
	// Skip to the first flag.
	for i < n && buf[i] != Flag {
		i++
	}
	for i < n {
		// buf[i] == Flag: candidate opening flag.
		j := i + 1
		for j < n && buf[j] != Flag {
			j++
		}
		if j >= n {
			// No closing flag yet: keep everything from the opening flag.
			return frames, buf[i:]
		}
		content := buf[i+1 : j]
		if len(content) > 0 {
			cp := make([]byte, len(content))
			copy(cp, content)
			frames = append(frames, cp)
		}
		// Reuse the closing flag as a possible opening flag of the next frame.
		i = j
	}
	return frames, nil
}
