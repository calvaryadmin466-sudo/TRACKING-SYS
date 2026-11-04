// Command simulator is a LABELLED JT/T 808 + JT/T 1078 device simulator for
// development and automated testing. It performs the real registration ->
// authentication -> heartbeat/location flow, and (Stage 4) responds to a 0x9101
// real-time A/V request by opening a video connection to the advertised media
// gateway and streaming JT/T 1078-framed packets.
//
// IMPORTANT: all data it sends is SIMULATED. The 1078 payload bytes are synthetic
// (they exercise the gateway's framing/metering, not a real codec) and every
// device is clearly labelled. Never treat simulator output as a real vehicle or a
// real camera feed.
package main

import (
	"bufio"
	"flag"
	"log"
	"math"
	"math/rand"
	"net"
	"time"

	"tracking/ingestion/internal/jt1078"
	"tracking/ingestion/internal/jt808"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:7808", "JT808 ingestion server address")
	id := flag.String("id", "100000000001", "device reporting ID (JT808 phone number)")
	count := flag.Int("count", 10, "location reports to send (0 = forever)")
	interval := flag.Duration("interval", 3*time.Second, "interval between location reports")
	lat := flag.Float64("lat", 22.5726, "starting latitude")
	lon := flag.Float64("lon", 88.3639, "starting longitude")
	use2019 := flag.Bool("v2019", false, "use JT/T 808-2019 header")
	plate := flag.String("plate", "SIM-DEMO-01", "simulated license plate")
	videoAddr := flag.String("video-addr", "", "stream 1078 directly to this gateway addr and exit (standalone)")
	videoChannel := flag.Int("video-channel", 1, "channel for standalone video streaming")
	videoCount := flag.Int("video-count", 100, "packets to stream (standalone or on 0x9101)")
	flag.Parse()

	log.SetFlags(log.LstdFlags | log.Lmicroseconds)

	// Standalone video mode: stream labelled 1078 packets to a gateway and exit.
	if *videoAddr != "" {
		log.Printf("=== SIMULATED 1078 VIDEO STREAM (NOT REAL FOOTAGE) ===")
		streamVideo(*videoAddr, *id, byte(*videoChannel), *videoCount)
		return
	}

	log.Printf("=== SIMULATED DEVICE (NOT A REAL VEHICLE) === id=SIM:%s server=%s", *id, *addr)
	conn, err := net.Dial("tcp", *addr)
	if err != nil {
		log.Fatalf("dial %s: %v", *addr, err)
	}
	defer conn.Close()
	reader := bufio.NewReader(conn)

	phone := jt808.EncodePhone(*id, *use2019)
	var version byte
	if *use2019 {
		version = 0x01
	}
	var serial uint16

	// Register + authenticate synchronously.
	serial++
	reg := jt808.Registration{ManufacturerID: "SIMUL", TerminalModel: "XV-900-8-SIM",
		TerminalID: "SIMSER1", PlateColor: 1, Plate: *plate}
	write(conn, jt808.BuildRegister(phone, *use2019, version, serial, reg), "register")
	authCode := awaitRegister(reader)
	log.Printf("auth code: %q", authCode)
	serial++
	write(conn, jt808.BuildAuth(phone, *use2019, version, serial, authCode), "auth")
	awaitOne(reader, "auth ack")

	// Background reader handles acks and unsolicited commands (e.g. 0x9101).
	go func() {
		for {
			fr, err := readFrame(reader)
			if err != nil {
				return
			}
			msg, err := jt808.DecodeFrame(fr)
			if err != nil {
				continue
			}
			if msg.Header.MsgID == jt808.MsgRealtimeAVRequest {
				if req, e := jt808.ParseRealtimeAVRequest(msg.Body); e == nil {
					log.Printf("<- 0x9101 realtime A/V request: ch=%d -> %s:%d (opening SIMULATED stream)",
						req.Channel, req.ServerIP, req.TCPPort)
					endpoint := net.JoinHostPort(req.ServerIP, itoa(int(req.TCPPort)))
					go streamVideo(endpoint, *id, req.Channel, *videoCount)
				}
			}
		}
	}()

	// Send heartbeat + location on an interval.
	clat, clon := *lat, *lon
	n := 0
	for *count == 0 || n < *count {
		serial++
		write(conn, jt808.BuildHeartbeat(phone, *use2019, version, serial), "heartbeat")
		serial++
		loc := jt808.Location{ACC: true, Positioned: true, Valid: true,
			Latitude: clat, Longitude: clon, Altitude: 12, Speed: 42.5,
			Heading: (n * 15) % 360, DeviceTime: time.Now().UTC(), Satellites: 11}
		write(conn, jt808.BuildLocation(phone, *use2019, version, serial, loc), "location")
		log.Printf("SIMULATED position #%d lat=%.6f lon=%.6f", n+1, clat, clon)
		clat += 0.0012 * math.Cos(float64(n))
		clon += 0.0012 * math.Sin(float64(n))
		n++
		if *count == 0 || n < *count {
			time.Sleep(*interval)
		}
	}
	time.Sleep(500 * time.Millisecond)
	log.Printf("done: sent %d SIMULATED location reports", n)
}

// streamVideo opens a TCP connection to the media gateway and sends labelled
// JT/T 1078 packets (I-frame then P-frames). The payload bytes are synthetic.
func streamVideo(endpoint, sim string, channel byte, packets int) {
	conn, err := net.Dial("tcp", endpoint)
	if err != nil {
		log.Printf("video dial %s failed: %v", endpoint, err)
		return
	}
	defer conn.Close()
	log.Printf("streaming %d SIMULATED 1078 packets to %s (sim=%s ch=%d)", packets, endpoint, sim, channel)
	var seq uint16
	ts := uint64(time.Now().UnixMilli())
	for i := 0; i < packets; i++ {
		seq++
		dataType := byte(jt1078.DataVideoPFrame)
		if i%15 == 0 {
			dataType = jt1078.DataVideoIFrame // keyframe every 15 packets
		}
		body := make([]byte, 400+rand.Intn(1200))
		rand.Read(body)
		pkt := &jt1078.Packet{PayloadType: 98, Mark: true, Sequence: seq, SIM: sim,
			Channel: channel, DataType: dataType, SubPackage: jt1078.SubAtomic,
			Timestamp: ts, LastIFrame: 40, LastFrame: 40, Body: body}
		if _, err := conn.Write(jt1078.Build(pkt)); err != nil {
			log.Printf("video write failed: %v", err)
			return
		}
		ts += 40
		time.Sleep(40 * time.Millisecond) // ~25 fps
	}
	log.Printf("finished streaming %d SIMULATED 1078 packets", packets)
}

func write(conn net.Conn, frame []byte, what string) {
	if _, err := conn.Write(frame); err != nil {
		log.Fatalf("write %s: %v", what, err)
	}
	log.Printf("-> %s (%d bytes)", what, len(frame))
}

func readFrame(r *bufio.Reader) ([]byte, error) {
	for {
		b, err := r.ReadByte()
		if err != nil {
			return nil, err
		}
		if b == jt808.Flag {
			break
		}
	}
	out := []byte{}
	for {
		b, err := r.ReadByte()
		if err != nil {
			return nil, err
		}
		if b == jt808.Flag {
			if len(out) == 0 {
				continue
			}
			return out, nil
		}
		out = append(out, b)
	}
}

func awaitOne(r *bufio.Reader, what string) {
	fr, err := readFrame(r)
	if err != nil {
		log.Fatalf("read %s: %v", what, err)
	}
	msg, _ := jt808.DecodeFrame(fr)
	if msg != nil {
		log.Printf("<- %s: %s", what, msg.Kind)
	}
}

func awaitRegister(r *bufio.Reader) string {
	fr, err := readFrame(r)
	if err != nil {
		log.Fatalf("read register resp: %v", err)
	}
	msg, err := jt808.DecodeFrame(fr)
	if err != nil || msg.Header.MsgID != jt808.MsgRegisterResp {
		log.Fatalf("expected register response: %v", err)
	}
	if len(msg.Body) < 3 || msg.Body[2] != jt808.RegResultSuccess {
		log.Fatalf("registration rejected")
	}
	return string(msg.Body[3:])
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var b [20]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}
