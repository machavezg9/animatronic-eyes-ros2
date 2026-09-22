# Animatronic Eyes — Raspberry Pi 5 / ROS 2

Six-axis animatronic eye mechanism with smooth motion, autonomous behaviours, and a
calibration-first workflow. This repository is the Python/ROS 2 continuation of a
working Arduino build.

**Arduino original:** https://github.com/machavezg9/animatronic_eyes
**Mechanism:** [Will Cogley's Simplified Eye Mechanism](https://www.instructables.com/Simplified-3D-Printed-Animatronic-Dual-Eye-Mechani/)

---

## Architecture

```
Intel RealSense D435/D455 ──► Jetson Orin Nano (8GB)          [Phase 4]
                                    │  YOLOv8 + depth
                                    │  ROS 2 Jazzy — person 3D position
                                    ▼
                          Raspberry Pi 5 + PCA9685 Bonnet      [this repo]
                                    │  servo control node
                                    ▼
                          6× SG90 (2 gaze axes + 4 eyelids)
```

### Layering

```
InputSource      nunchuck / null / (later) ROS subscriber
    │            emits GazeCommand — normalized −1..1, device calibration stays inside
    ▼
StateMachine     STARTUP → ACTIVE ⇄ IDLE
    │
    ▼
EyeController    gaze + eyelid targets, smoothing, blink
    │            normalized units → calibrated ticks
    ▼
Servo            calibrated clamp → absolute clamp → slew limit
    │
    ▼
PWMBackend       PCA9685Backend (hardware) | MockBackend (any machine)
```

Two seams do the load-bearing work. `InputSource` means the Jetson's vision node
arrives as one new implementation, with nothing below it changed. `PWMBackend` means
the whole system runs and is testable on a machine with no PCA9685 — or no I²C bus at
all.

---

## Why raw 12-bit ticks

Every position in `config/eyes.yaml` is a raw PCA9685 tick value at 60 Hz, exactly as
calibrated on the Arduino. The Bonnet uses the same PCA9685 chip as the Arduino shield,
so `duty_cycle = ticks << 4` is bit-identical to the Arduino's
`pwm.setPWM(channel, 0, ticks)`.

This is deliberate, and it's why `adafruit_motor.servo` and every other angle- or
microsecond-based API is avoided: those re-derive pulse widths from their own
assumptions and would silently discard per-servo calibration that was measured against
a real mechanism.

---

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

.venv/bin/animatronic-eyes validate                  # check config, print calibration
.venv/bin/animatronic-eyes run --backend mock        # full system, no hardware
.venv/bin/python -m pytest
```

`--backend mock` is a supported way to run, not a stub. It records every channel write,
so the startup choreography, idle transition, and blink timing are all observable
without servos attached.

### On hardware (Raspberry Pi 5)

```bash
sudo raspi-config nonint do_i2c 0        # or dtparam=i2c_arm=on in /boot/firmware/config.txt
i2cdetect -y 1                           # expect 0x40 (Bonnet), 0x52 (nunchuck)

.venv/bin/pip install -e '.[hardware]'
```

Power the servo rail from an external 5 V supply with a common ground. **Never run six
servos off USB.**

Bring each channel up individually before running the full system:

```bash
animatronic-eyes selftest --servo horizontal     # center → min → center → max → center
animatronic-eyes selftest --servo left_upper
# ... and so on for all six
```

Listen for buzzing or straining at the extremes. Either means the calibrated bounds no
longer match the mechanism — stop and recalibrate rather than letting it run.

```bash
animatronic-eyes run --backend pca9685 --input null       # autonomous only
animatronic-eyes run --backend pca9685 --input nunchuck   # manual control
```

---

## Configuration

`config/eyes.yaml` is the single source of truth: channel assignments, calibrated pulse
bounds, inversion flags, smoothing, safety limits, and behaviour timing. Nothing is
hardcoded in the control path.

Inversion is handled in software — a servo mounted backwards is a config flag, not a
rewiring job.

The configuration is validated as a whole at load, not field by field, so problems that
only exist in combination get caught before anything moves: a centre outside its own
travel, two servos on one channel, a deadzone that swallows the joystick range, a blink
longer than its own idle interval. Failures name the setting and what to do about it.

### Safety

Three independent layers, applied to every write in order:

1. **Calibrated clamp** — per-channel bounds measured on the real mechanism
2. **Absolute clamp** — a configuration-independent net (100–650 ticks)
3. **Slew limit** — max change per update, so a bad target can't become a full-speed
   slam into a hard stop

Shutdown is guaranteed on normal exit, Ctrl-C, or SIGTERM: eyes recentre, lids open,
PWM output released. No servo is left holding a strained position.

---

## Controls (nunchuck)

| Input | Action |
|---|---|
| Joystick | Move eyes |
| Z | Blink |
| C | Recentre |
| 15 s idle | Autonomous behaviours begin |

Any input exits idle instantly. Activity detection runs before state handling every
frame, so the frame that first sees input is the frame that acts on it.

---

## Behaviours

**Startup** (~4.7 s): close → hold → open → look around (L/R/U/D) → centre.

**Idle**: randomized gaze shifts every 2–4 s bounded to 70% of each axis's range, plus
auto-blink every 2–6 s. Randomized intervals are what keep it from reading as a loop.

---

## Project phases

- [x] **Phase 1** — Arduino UNO: 6-servo control, nunchuck, calibration, behaviours
- [x] **Phase 2a** — Port to Python / Raspberry Pi 5 + PCA9685 Bonnet
- [ ] **Phase 2b** — Hardware validation: per-channel bring-up, parity against Arduino
- [ ] **Phase 3** — Motion planner: saccade vs. smooth-pursuit profiles, eased blink
- [ ] **Phase 4** — Vision: Jetson Orin Nano + RealSense + YOLOv8 over ROS 2 Jazzy

---

## Development

Requires Python 3.11+. The `hardware` extra (Blinka, `adafruit-circuitpython-pca9685`)
is only needed on the Pi — everything else, including the full test suite, runs
anywhere.

```bash
.venv/bin/python -m pytest
```

---

## License

MIT
