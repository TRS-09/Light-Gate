"""Raspberry Pi Pico (RP2040) Ball-Drop Precision Stopwatch.
Applies two-parameter hardware calibration (slope + offset) to yield 
consistent g = 9.81 m/s2 across variable heights.

Wiring:
  GP12: Magnet Driver (LOW = Hold, HIGH = Release)
  GP10: Light Beam Sensor (HIGH = Beam Broken)
  GP2 : GO Button (Pull-Up to GND)
  GP16: RESET Button (Pull-Up to GND)
  GP4 : OLED SDA (Hardware I2C0)
  GP5 : OLED SCL (Hardware I2C0)
"""

import time
import micropython
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C

micropython.alloc_emergency_exception_buf(100)

CORRECTION_SLOPE = 1.0069
CORRECTION_OFFSET_US = 12200  # 12.20 ms total delay subtraction

MAGNET_PIN = 12
COMPARATOR_PIN = 10
GO_BUTTON_PIN = 2
RESET_BUTTON_PIN = 16
OLED_SDA_PIN = 4
OLED_SCL_PIN = 5
OLED_ADDRESS = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 32

MAGNET_HOLD_LEVEL = 0
MAGNET_RELEASE_LEVEL = 1
BEAM_BROKEN_LEVEL = 1

BUTTON_DEBOUNCE_MS = 35
EDGE_GUARD_US = 100

HOLDING = 0
TIMING = 1
FINISHED = 2

magnet = Pin(MAGNET_PIN, Pin.OUT, value=MAGNET_HOLD_LEVEL)
comparator = Pin(COMPARATOR_PIN, Pin.IN)
go_button = Pin(GO_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
reset_button = Pin(RESET_BUTTON_PIN, Pin.IN, Pin.PULL_UP)


def setup_oled():
    try:
        i2c = I2C(0, sda=Pin(OLED_SDA_PIN), scl=Pin(OLED_SCL_PIN), freq=400_000)
        devices = i2c.scan()
        if OLED_ADDRESS not in devices:
            print("OLED missing at address 0x%02X" % OLED_ADDRESS)
            return None
        return SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDRESS)
    except OSError as error:
        print("I2C Hardware Error:", error)
        return None


oled = setup_oled()


def screen(*lines):
    if oled is None:
        return
    oled.fill(0)
    for row, line in enumerate(lines[:4]):
        oled.text(str(line)[:16], 0, row * 8)
    oled.show()


state = HOLDING
start_us = 0
stop_us = None
last_edge_us = 0


def comparator_edge(pin):
    """Microsecond ISR triggered when leading edge breaks light beam."""
    global state, stop_us, last_edge_us

    now = time.ticks_us()
    if (
        state == TIMING
        and pin.value() == BEAM_BROKEN_LEVEL
        and time.ticks_diff(now, last_edge_us) >= EDGE_GUARD_US
    ):
        stop_us = now
        last_edge_us = now
        state = FINISHED


if BEAM_BROKEN_LEVEL:
    comparator.irq(trigger=Pin.IRQ_RISING, handler=comparator_edge)
else:
    comparator.irq(trigger=Pin.IRQ_FALLING, handler=comparator_edge)


def raw_elapsed_us():
    """Raw timing measured directly from GPIO hardware interrupt."""
    if state == TIMING:
        return time.ticks_diff(time.ticks_us(), start_us)
    if stop_us is not None:
        return time.ticks_diff(stop_us, start_us)
    return None


def elapsed_us():
    """Adjusted output time taking coil lag and beam dynamics into account."""
    raw = raw_elapsed_us()
    if raw is None:
        return None
    
    # t_adj = (slope * t_raw) - offset
    adjusted = int((CORRECTION_SLOPE * raw) - CORRECTION_OFFSET_US)
    return max(0, adjusted)


def refresh_screen():
    if state == HOLDING:
        screen("READY", "Magnet: ARMED", "", "Press to DROP")
    elif state == TIMING:
        screen("TIMING...", "Ball dropping", "", "Waiting beam...")
    else:
        duration_us = elapsed_us()
        if duration_us is None:
            screen("TIME ERROR", "", "", "Press to RE-ARM")
        else:
            sec = duration_us / 1_000_000.0
            ms = duration_us / 1_000.0
            screen(
                "TIME RECORDED:",
                "t: %.4f s" % sec,
                "   %.2f ms" % ms,
                "Press to RE-ARM"
            )


def begin_drop():
    global state, start_us, stop_us

    if comparator.value() == BEAM_BROKEN_LEVEL:
        print("Release blocked: Light beam obstructed!")
        return

    stop_us = None
    start_us = time.ticks_us()
    magnet.value(MAGNET_RELEASE_LEVEL)
    state = TIMING
    print("Ball released. Timing active...")


def reset_to_holding():
    global state, stop_us

    magnet.value(MAGNET_HOLD_LEVEL)
    stop_us = None
    state = HOLDING
    print("Magnet re-armed. READY.")


# Debounce trackers
go_raw = go_button.value()
go_stable = go_raw
go_changed_ms = time.ticks_ms()

reset_raw = reset_button.value()
reset_stable = reset_raw
reset_changed_ms = time.ticks_ms()


def get_button_press():
    global go_raw, go_stable, go_changed_ms
    global reset_raw, reset_stable, reset_changed_ms

    now = time.ticks_ms()
    pressed = False

    # GO Button
    reading = go_button.value()
    if reading != go_raw:
        go_raw = reading
        go_changed_ms = now
    if go_stable != go_raw and time.ticks_diff(now, go_changed_ms) >= BUTTON_DEBOUNCE_MS:
        go_stable = go_raw
        if go_stable == 0:
            pressed = True

    # RESET Button
    reading = reset_button.value()
    if reading != reset_raw:
        reset_raw = reading
        reset_changed_ms = now
    if reset_stable != reset_raw and time.ticks_diff(now, reset_changed_ms) >= BUTTON_DEBOUNCE_MS:
        reset_stable = reset_raw
        if reset_stable == 0:
            pressed = True

    return pressed


# Startup
refresh_screen()
print("RP2040 Precision Timer Active")
print("Calibration: Slope=%.4f | Offset=%d us" % (CORRECTION_SLOPE, CORRECTION_OFFSET_US))

last_screen_ms = time.ticks_ms()
last_reported_state = None

while True:
    if get_button_press():
        if state == HOLDING:
            begin_drop()
            refresh_screen()
        elif state == FINISHED:
            reset_to_holding()
            refresh_screen()

    if state != last_reported_state:
        if state == FINISHED:
            raw = raw_elapsed_us() or 0
            adj = elapsed_us() or 0
            print("--- RESULT ---")
            print("Raw Time     :", raw, "us (%.2f ms)" % (raw / 1000.0))
            print("Adjusted Time:", adj, "us | %.3f ms | %.4f s" % (adj / 1000.0, adj / 1000000.0))
            refresh_screen()
        last_reported_state = state

    now_ms = time.ticks_ms()
    if time.ticks_diff(now_ms, last_screen_ms) >= 100:
        refresh_screen()
        last_screen_ms = now_ms

    time.sleep_ms(2)