package jt808

import (
	"encoding/binary"
	"fmt"
)

// Video-related JT/T 808 message IDs (platform -> terminal unless noted).
const (
	MsgRealtimeAVRequest uint16 = 0x9101 // start real-time audio/video
	MsgAVControl         uint16 = 0x9102 // control/stop real-time stream
	MsgPlaybackRequest   uint16 = 0x9201 // remote playback request
	MsgQueryResourceList uint16 = 0x9205 // query stored A/V resource list
	MsgResourceList      uint16 = 0x1205 // terminal -> platform resource list
)

// AV data types for 0x9101 (data_type field).
const (
	AVAudioVideo     byte = 0
	AVVideoOnly      byte = 1
	AVTwoWayTalk     byte = 2
	AVMonitor        byte = 3
	AVCentralBcast   byte = 4
	AVTransparent    byte = 5
)

// Stream types.
const (
	StreamMain byte = 0
	StreamSub  byte = 1
)

func init() {
	messageNames[MsgRealtimeAVRequest] = "realtime_av_request"
	messageNames[MsgAVControl] = "av_control"
	messageNames[MsgPlaybackRequest] = "playback_request"
	messageNames[MsgQueryResourceList] = "query_resource_list"
	messageNames[MsgResourceList] = "resource_list"
}

// BuildRealtimeAVRequest builds a 0x9101 message instructing the terminal to open
// a real-time A/V stream for a channel to the given media server endpoint.
func BuildRealtimeAVRequest(phoneBCD []byte, hasVersion bool, version byte, serial uint16,
	serverIP string, tcpPort, udpPort uint16, channel, dataType, streamType byte) []byte {
	ip := []byte(serverIP)
	body := make([]byte, 0, 1+len(ip)+7)
	body = append(body, byte(len(ip)))
	body = append(body, ip...)
	body = binary.BigEndian.AppendUint16(body, tcpPort)
	body = binary.BigEndian.AppendUint16(body, udpPort)
	body = append(body, channel, dataType, streamType)
	return buildFrame(MsgRealtimeAVRequest, phoneBCD, hasVersion, version, serial, body)
}

// BuildAVControl builds a 0x9102 message to control an active real-time stream.
// command: 0 close, 1 switch stream, 2 pause, 3 resume, 4 close two-way talk.
func BuildAVControl(phoneBCD []byte, hasVersion bool, version byte, serial uint16,
	channel, command, closeType, switchStreamType byte) []byte {
	body := []byte{channel, command, closeType, switchStreamType}
	return buildFrame(MsgAVControl, phoneBCD, hasVersion, version, serial, body)
}

// BuildPlaybackRequest builds a 0x9201 remote video playback request.
// startTime/endTime are 6-byte BCD YYMMDDhhmmss.
func BuildPlaybackRequest(phoneBCD []byte, hasVersion bool, version byte, serial uint16,
	serverIP string, tcpPort, udpPort uint16, channel, mediaType, streamType, storageType,
	playbackMode, fastForward byte, startBCD, endBCD []byte) []byte {
	ip := []byte(serverIP)
	body := make([]byte, 0, 1+len(ip)+7+12)
	body = append(body, byte(len(ip)))
	body = append(body, ip...)
	body = binary.BigEndian.AppendUint16(body, tcpPort)
	body = binary.BigEndian.AppendUint16(body, udpPort)
	body = append(body, channel, mediaType, streamType, storageType, playbackMode, fastForward)
	body = append(body, fixedBCD(startBCD)...)
	body = append(body, fixedBCD(endBCD)...)
	return buildFrame(MsgPlaybackRequest, phoneBCD, hasVersion, version, serial, body)
}

// BuildQueryResourceList builds a 0x9205 remote video resource list query packet.
// channel: logical channel (0=all, 1..64)
// startBCD/endBCD: 6-byte BCD YYMMDDhhmmss
// alarmFlag: 8-byte uint64 alarm type bitmask (0 = no filter)
// mediaType: 0 audio/video, 1 audio, 2 video, 3 audio or video
// streamType: 0 all, 1 main stream, 2 sub stream
// storageType: 0 all, 1 disk/primary, 2 backup/SD
func BuildQueryResourceList(phoneBCD []byte, hasVersion bool, version byte, serial uint16,
	channel byte, startBCD, endBCD []byte, alarmFlag uint64, mediaType, streamType, storageType byte) []byte {
	body := make([]byte, 0, 1+12+8+3)
	body = append(body, channel)
	body = append(body, fixedBCD(startBCD)...)
	body = append(body, fixedBCD(endBCD)...)
	body = binary.BigEndian.AppendUint64(body, alarmFlag)
	body = append(body, mediaType, streamType, storageType)
	return buildFrame(MsgQueryResourceList, phoneBCD, hasVersion, version, serial, body)
}

// RealtimeAVRequest is a decoded 0x9101 body (used by the simulator/tests).
type RealtimeAVRequest struct {
	ServerIP   string
	TCPPort    uint16
	UDPPort    uint16
	Channel    byte
	DataType   byte
	StreamType byte
}

// ParseRealtimeAVRequest decodes a 0x9101 body.
func ParseRealtimeAVRequest(body []byte) (*RealtimeAVRequest, error) {
	if len(body) < 1 {
		return nil, fmt.Errorf("jt808: 9101 body empty")
	}
	n := int(body[0])
	if len(body) < 1+n+7 {
		return nil, fmt.Errorf("jt808: 9101 body too short")
	}
	off := 1
	ip := string(body[off : off+n])
	off += n
	r := &RealtimeAVRequest{
		ServerIP:   ip,
		TCPPort:    binary.BigEndian.Uint16(body[off : off+2]),
		UDPPort:    binary.BigEndian.Uint16(body[off+2 : off+4]),
		Channel:    body[off+4],
		DataType:   body[off+5],
		StreamType: body[off+6],
	}
	return r, nil
}

func fixedBCD(b []byte) []byte {
	out := make([]byte, 6)
	copy(out, b)
	return out
}
