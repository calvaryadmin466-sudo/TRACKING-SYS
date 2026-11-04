package jt808

import "sort"

// alarmBitNames maps JT/T 808 0x0200 alarm-flag bit positions to stable event
// names (JT/T 808-2013 Table 24). Only documented bits are named; unknown bits
// are reported generically so nothing is silently lost.
var alarmBitNames = map[int]string{
	0:  "emergency_sos",
	1:  "overspeed",
	2:  "fatigue_driving",
	3:  "danger_warning",
	4:  "gnss_module_fault",
	5:  "gnss_antenna_disconnected",
	6:  "gnss_antenna_short_circuit",
	7:  "main_power_undervoltage",
	8:  "main_power_off",
	9:  "lcd_fault",
	10: "tts_module_fault",
	11: "camera_fault",
	12: "ic_card_fault",
	13: "overspeed_warning",
	14: "fatigue_warning",
	18: "cumulative_driving_timeout",
	19: "overtime_parking",
	20: "geofence_in_out",
	21: "route_in_out",
	22: "route_time_abnormal",
	23: "route_deviation",
	24: "vss_fault",
	25: "fuel_abnormal",
	26: "vehicle_stolen",
	27: "illegal_ignition",
	28: "illegal_displacement",
	29: "collision_warning",
	30: "rollover_warning",
	31: "illegal_door_open",
}

// AlarmNames returns the named alarms represented by the set bits of a 0x0200
// alarm flag, in ascending bit order. Unnamed set bits are returned as
// "alarm_bitN" so they are surfaced rather than dropped.
func AlarmNames(flag uint32) []string {
	if flag == 0 {
		return nil
	}
	var bits []int
	for i := 0; i < 32; i++ {
		if flag&(1<<uint(i)) != 0 {
			bits = append(bits, i)
		}
	}
	sort.Ints(bits)
	out := make([]string, 0, len(bits))
	for _, b := range bits {
		if name, ok := alarmBitNames[b]; ok {
			out = append(out, name)
		} else {
			out = append(out, "alarm_bit"+itoa(b))
		}
	}
	return out
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b [12]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}
