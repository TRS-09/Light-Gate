# Raspberry Pi Pico Light Gate

A system consisting of a precision light gate for the measurement of the acceleration due to gravity.

A ball is held and released by means of an electromagnet. As soon as the ball is released, the Raspberry Pi Pico begins a timer. The timer stops when the ball goes through the light gate. The time that has been measured is then used in co-operation with the distance (measured with a millimeter ruler) to calculate the acceleration due to gravity.

## How it works

1. The electromagnet keeps the ball in place.
2. The DROP button is pressed.
3. The Pico switches off the electromagnet and then begins the timer.
4. The ball passes through the light gate.
5. The light gate picks up the ball and transmits a signal to the Pico.
6. The timer will stop as soon as the beam is broken.
7. The OLED screen shows the measured time.
As a result, the result is saved, allowing the previous six measurements to be viewed.

The second button allows you to see the most recent six measurements, and if you press it for one second the results which have been stored will be cleared.

## Hardware

* Raspberry Pi Pico / RP2040
* Electromagnet
* Light gate / beam sensor
* OLED display
* 2 push buttons
* Electromagnet driver circuit
* Ball for the experiment
* 3D printed components

## Pin connections

| Pico pin | Function               |
| -------- | ---------------------- |
| GP2      | Drop / re-arm button   |
| GP4      | OLED SDA               |
| GP5      | OLED SCL               |
| GP10     | Light gate sensor      |
| GP12     | Electromagnet control  |
| GP16     | History / clear button |

The electromagnet is not controlled directly from the Pico GPIO but instead via a driver circuit involving a 2N2222 transistor, this is due to the IRLZ44N MOSFET not being able to fully engage with the 3.3v from the PICO (increasing resistance of MOSFET, reducing efficiency and causing MOSFET to get hot).

## Controls

### Drop button (GP2)

* Press when ready → releases the ball and starts timing
* Press after a measurement → re-arms the electromagnet

### History button (GP16)

* Short press → displays the previous six measurements
* Hold for 1 second → clears the stored measurements

## Timing

The Pico detects when the ball breaks the light beam by means of a GPIO interrupt, which enables the timer to stop without it being necessary for the main program loop to detect the event.

The time measured is recorded in microseconds and then converted into seconds for the purpose of the displayed result.

A minor calibration adjustment is made to compensate for the delays in the release and detection system.

## Results

The system was tested by measuring the value of gravitational acceleration.

The calculated value was:

**g = 9.8077 m/s²**

This is very close to the expected value of approximately:

**g = 9.81 m/s²**

The other difference was minor and fell within the experimental uncertainty of the setup.

## 3D Model

The Autodesk Fusion program can open the *.f3d file, which contains the Fusion 360 model of the light-gate assembly.

## Files

* main.py – a MicroPython program for the Raspberry Pi Pico
* ssd1306.py - contains driver and setup code for OLED screen
* `*.f3d` is a Fusion 360 CAD model file
Information about the project in the README.md file

## Notes

The timing system is specifically designed for this experimental arrangement and the calibration values in the program take into account the delays caused by the electromagnet and light-gate system.
`
