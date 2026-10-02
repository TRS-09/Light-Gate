"""Raspberry Pi Pico ball-drop timer.

GP2: Releases the ball / re-arms the magnet.
GP16:
  Short press: Shows the last 6 times.
  Hold for 1 second: Clears the history.

GP12: Magnet (LOW = hold, HIGH = release)
GP10: Light beam sensor (HIGH = beam broken)
GP4 : OLED SDA
GP5 : OLED SCL
"""

import time
import micropython
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C

micropython.alloc_emergency_exception_buf(100)

# Calibration values
CORRECTION_SLOPE = 1.0069
CORRECTION_OFFSET_US = 12200

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
HOLD_CLEAR_MS = 1000

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

# Stores the most recent six results
recorded_times = []
show_history = False


def draw_history_screen():
    """Show the last six times on the OLED."""
    if oled is None:
        return
    oled.fill(0)
    oled.text("LAST 6 TIMES (s)", 0, 0)

    # Three results on each side of the screen
    for i in range(6):
        col = 0 if i < 3 else 64
        row_y = 8 + (i % 3) * 8
        prefix = "%d:" % (i + 1)

        if i < len(recorded_times):
            val_str = "%.4f" % recorded_times[i]
            entry_str = prefix + val_str
        else:
            entry_str = prefix + "------"

        oled.text(entry_str[:8], col, row_y)

    oled.show()


def comparator_edge(pin):
    """Record the time when the ball breaks the beam."""
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
    """Get the measured time before calibration is applied."""
    if state == TIMING:
        return time.ticks_diff(time.ticks_us(), start_us)
    if stop_us is not None:
        return time.ticks_diff(stop_us, start_us)
    return None


def elapsed_us():
    """Apply the calibration to the measured time."""
    raw = raw_elapsed_us()
    if raw is None:
        return None

    adjusted = int((CORRECTION_SLOPE * raw) - CORRECTION_OFFSET_US)
    return max(0, adjusted)


def refresh_screen():
    if show_history:
        draw_history_screen()
        return

    if state == HOLDING:
        screen("READY", "Magnet: ARMED", "", "GP2: DROP")
    elif state == TIMING:
        screen("TIMING...", "Ball dropping", "", "Waiting beam...")
    else:
        duration_us = elapsed_us()
        if duration_us is None:
            screen("TIME ERROR", "", "", "GP2: RE-ARM")
        else:
            sec = duration_us / 1_000_000.0
            screen(
                "TIME RECORDED:",
                "t: %.4f s" % sec,
                "",
                "GP2: RE-ARM"
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


# Variables used to debounce the buttons
go_raw = go_button.value()
go_stable = go_raw
go_changed_ms = time.ticks_ms()

reset_raw = reset_button.value()
reset_stable = reset_raw
reset_changed_ms = time.ticks_ms()
reset_press_start_ms = 0
reset_held_action_done = False


def check_buttons():
    global go_raw, go_stable, go_changed_ms
    global reset_raw, reset_stable, reset_changed_ms
    global reset_press_start_ms, reset_held_action_done

    now = time.ticks_ms()
    go_pressed = False
    reset_short_pressed = False
    reset_long_held = False

    # GP2 button
    reading = go_button.value()
    if reading != go_raw:
        go_raw = reading
        go_changed_ms = now
    if go_stable != go_raw and time.ticks_diff(now, go_changed_ms) >= BUTTON_DEBOUNCE_MS:
        go_stable = go_raw
        if go_stable == 0:
            go_pressed = True

    # GP16 button
    reading = reset_button.value()
    if reading != reset_raw:
        reset_raw = reading
        reset_changed_ms = now
    if reset_stable != reset_raw and time.ticks_diff(now, reset_changed_ms) >= BUTTON_DEBOUNCE_MS:
        reset_stable = reset_raw
        if reset_stable == 0:
            reset_press_start_ms = now
            reset_held_action_done = False
        else:
            if not reset_held_action_done:
                if time.ticks_diff(now, reset_press_start_ms) < HOLD_CLEAR_MS:
                    reset_short_pressed = True

    # Check if GP16 has been held for long enough
    if reset_stable == 0 and not reset_held_action_done:
        if time.ticks_diff(now, reset_press_start_ms) >= HOLD_CLEAR_MS:
            reset_long_held = True
            reset_held_action_done = True

    return go_pressed, reset_short_pressed, reset_long_held


refresh_screen()
print("RP2040 Precision Timer Active")
print("Calibration: Slope=%.4f | Offset=%d us" % (CORRECTION_SLOPE, CORRECTION_OFFSET_US))

last_screen_ms = time.ticks_ms()
last_reported_state = None

while True:
    go_pressed, reset_short_pressed, reset_long_held = check_buttons()

    # Hold GP16 to clear the saved times
    if reset_long_held:
        recorded_times.clear()
        screen("HISTORY CLEARED", "", "", "Memory reset")
        time.sleep_ms(800)
        refresh_screen()

    # Short press GP16 to switch history on/off
    elif reset_short_pressed:
        show_history = not show_history
        refresh_screen()

    # GP2 releases the ball or re-arms the magnet
    elif go_pressed:
        if show_history:
            show_history = False
        if state == HOLDING:
            begin_drop()
            refresh_screen()
        elif state == FINISHED:
            reset_to_holding()
            refresh_screen()

    # Save the result when a drop has finished
    if state != last_reported_state:
        if state == FINISHED:
            raw = raw_elapsed_us() or 0
            adj = elapsed_us() or 0
            if adj > 0:
                sec = adj / 1_000_000.0
                recorded_times.append(sec)
                if len(recorded_times) > 6:
                    recorded_times.pop(0)

            print("--- RESULT ---")
            print("Raw Time     :", raw, "us (%.2f ms)" % (raw / 1000.0))
            print("Adjusted Time:", adj, "us | %.4f s" % (adj / 1000000.0))
            refresh_screen()
        last_reported_state = state

    now_ms = time.ticks_ms()
    if time.ticks_diff(now_ms, last_screen_ms) >= 100:
        refresh_screen()
        last_screen_ms = now_ms

    time.sleep_ms(2)
