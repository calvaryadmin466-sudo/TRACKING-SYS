// Command loadtest spawns many simulated JT/T 808 devices against the ingestion
// server to measure how it behaves under concurrent connections and position
// throughput. All data is SIMULATED and clearly labelled; never point this at a
// production server carrying real fleets.
//
// Example:
//   go run ./cmd/loadtest -addr 127.0.0.1:7808 -devices 1000 -interval 10s -duration 2m
package main

import (
	"flag"
	"log"
	"math/rand"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"tracking/ingestion/internal/jt808"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:7808", "ingestion server address")
	devices := flag.Int("devices", 100, "number of simulated devices")
	interval := flag.Duration("interval", 10*time.Second, "position report interval per device")
	duration := flag.Duration("duration", 60*time.Second, "total run time")
	rampup := flag.Duration("rampup", 10*time.Second, "spread connections over this period")
	base := flag.Int64("base-id", 900000000000, "base reporting ID (simulated range)")
	flag.Parse()

	log.Printf("=== SIMULATED LOAD TEST (NOT REAL VEHICLES) === devices=%d addr=%s", *devices, *addr)
	var connected, positions, failures atomic.Int64
	var wg sync.WaitGroup
	deadline := time.Now().Add(*duration)

	for i := 0; i < *devices; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			// Stagger connects across the ramp-up window.
			time.Sleep(time.Duration(float64(*rampup) * float64(idx) / float64(*devices)))
			id := itoa(*base + int64(idx))
			if err := runDevice(*addr, id, *interval, deadline, &positions); err != nil {
				failures.Add(1)
				return
			}
			connected.Add(1)
		}(i)
	}

	// Periodic progress.
	done := make(chan struct{})
	go func() {
		t := time.NewTicker(5 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-done:
				return
			case <-t.C:
				log.Printf("progress: connected=%d positions=%d failures=%d",
					connected.Load(), positions.Load(), failures.Load())
			}
		}
	}()

	wg.Wait()
	close(done)
	log.Printf("DONE: devices=%d connected_ok=%d positions_sent=%d failures=%d",
		*devices, connected.Load(), positions.Load(), failures.Load())
}

func runDevice(addr, id string, interval time.Duration, deadline time.Time, positions *atomic.Int64) error {
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		return err
	}
	defer conn.Close()
	phone := jt808.EncodePhone(id, false)
	var serial uint16

	serial++
	reg := jt808.Registration{ManufacturerID: "LOAD", TerminalModel: "SIM", TerminalID: "LT" + id[len(id)-4:]}
	if _, err := conn.Write(jt808.BuildRegister(phone, false, 0, serial, reg)); err != nil {
		return err
	}
	serial++
	if _, err := conn.Write(jt808.BuildAuth(phone, false, 0, serial, "LOADTEST")); err != nil {
		return err
	}
	// Drain responses in the background; we only care about send throughput here.
	go func() { buf := make([]byte, 4096); for { if _, e := conn.Read(buf); e != nil { return } } }()

	lat, lon := 22.5+rand.Float64()*0.2, 88.3+rand.Float64()*0.2
	for time.Now().Before(deadline) {
		serial++
		_, _ = conn.Write(jt808.BuildHeartbeat(phone, false, 0, serial))
		serial++
		loc := jt808.Location{ACC: true, Positioned: true, Valid: true, Latitude: lat, Longitude: lon,
			Speed: 40, Heading: 90, DeviceTime: time.Now().UTC(), Satellites: 10}
		if _, err := conn.Write(jt808.BuildLocation(phone, false, 0, serial, loc)); err != nil {
			return err
		}
		positions.Add(1)
		lat += 0.0005
		lon += 0.0005
		time.Sleep(interval)
	}
	return nil
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	var b [24]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}
