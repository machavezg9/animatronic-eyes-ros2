# Animatronic Eyes — Project Context for Claude Code

**Purpose of this document:** Context handoff so Claude Code can pick up this project without re-deriving decisions already made in planning. Treat everything below as settled unless the user says otherwise.

---

## Project Goal

Building an animatronic eye mechanism with computer-vision-driven person tracking, as a portfolio piece targeting **Walt Disney Imagineering Show Engineer** positions. The project is meant to demonstrate professional-grade embedded systems and robotics engineering aligned with Disney's animatronics standards — natural, lifelike character motion, not just functional servo control.

**End goal:** a vision system that locks onto the first person it sees, tracks them within FOV, and maps that tracking to eye movement (plus, longer-term, voice/audio behaviors that make the character feel alive).

### Project Breakdown
- **Part 1:** Vision system that tracks a person within FOV, locking onto the first person detected
- **Part 2:** Integrate that tracking output with the animatronic eye servos — map 3D person position to eye motion

---

## Architecture Decision (Final)

```
Intel RealSense D435/D455 → Jetson Orin Nano (8GB)
                                   │  YOLOv8 person detection + depth
                                   │  ROS 2 (Jazzy) — publishes person 3D position
                                   ▼
                          Raspberry Pi 5 + PWM HAT
                                   │  ROS 2 (Jazzy) — servo control node
                                   │  Subscribes to person position topic
                                   ▼
                          6x SG90 servos (eyeballs + eyelids)
```

**Why this architecture** (context for design decisions going forward):
- Full ROS 2 split keeps vision and motor control as independent, professionally-architected nodes — not a serial-bridge hack
- Depth data (RealSense) enables eye convergence behavior (eyes cross slightly when tracking a close subject) — a natural-motion detail Disney-caliber animatronics prioritize
- Architecture scales cleanly to future additions (voice synthesis, idle behaviors, multi-modal reactions) as new ROS nodes, without touching existing servo or vision code

---

## Hardware Inventory

| Component | Status |
|---|---|
| Arduino UNO R3 | Owned — original working prototype platform |
| Raspberry Pi 4 | Owned |
| Raspberry Pi 5 | Owned — target for servo control node |
| Jetson Nano (original) | Owned — superseded by Orin Nano for this project |
| **Jetson Orin Nano (8GB)** | **Decided purchase** — vision compute |
| **Intel RealSense D435/D455** | **Decided purchase** — depth camera |
| Adafruit 16-Channel PWM Servo Shield (Arduino) | Owned — original Arduino build |
| Adafruit 16-Channel PWM HAT (#2327) | Owned |
| Adafruit 16-Channel PWM/Servo Bonnet (#3416) | Owned — **preferred for this build** (smaller footprint, same PCA9685 chip, same calibration values transfer) |
| SG90 servos (×6) | Owned, calibrated — 2x eyeball (horizontal/vertical), 4x independent eyelids |
| Wii Nunchuck controllers | Owned — used for manual test/control input |
| 3D printing access | Available |

---

## Software Stack

- **C++** — original Arduino embedded codebase (object-oriented, state-machine driven)
- **Arduino IDE + Adafruit_PWMServoDriver** — original servo control
- **Adafruit PCA9685 libraries** (Python, for Pi migration) — same underlying chip as Arduino shield, so calibration values (pulse widths, inversion settings) carry over unchanged
- **ROS 2 Jazzy** — on both Jetson and Pi (matched distro, one DDS network, no bridging)
- **YOLOv8** — person detection on Jetson
- **librealsense / realsense-ros** — depth camera integration

### OS Decisions
| Board | OS | Notes |
|---|---|---|
| Jetson Orin Nano | **JetPack 7.2.1** (Ubuntu 24.04, L4T r39.2.1) | Current release; matches ROS 2 Jazzy tier-1 support; Isaac ROS validated against this combo. Flash via Jetson ISO on USB (SD card images no longer supported as of JetPack 7.2). Fallback if driver issues arise: JetPack 6.2.2 (Ubuntu 22.04) + ROS 2 Humble — more mature/documented, but off the current-gen path. |
| Raspberry Pi 5 | **Ubuntu Server 24.04 LTS (64-bit)** — **not** Raspberry Pi OS | ROS 2 has no official binaries for Raspberry Pi OS/Debian; Ubuntu Server gets `apt install ros-jazzy-*` directly and matches the Jetson's distro exactly. Headless (no desktop) is fine — this board only runs the servo control node. |

---

## Migration History (What's Already Done)

1. **Phase 1 (complete):** Working Arduino UNO system — 6-servo control via Adafruit PWM shield, Wii Nunchuck manual input, calibrated pulse-width ranges + inversion settings per servo, startup animations, autonomous idle behaviors with randomized movement, auto-blink, smooth state transitions.
2. **Phase 2 (in progress):** Migrating servo control from Arduino (C++) to Raspberry Pi 5 (Python, via PWM Bonnet #3416), preserving the existing object-oriented architecture and all calibration work.
3. **Phase 3 (planned):** Vision system on Jetson Orin Nano + RealSense, ROS 2 Jazzy bridging vision → servo control, full person-tracking integration.

---

## Engineering Principles to Maintain

These are established working principles for this project — carry them into all new code:

- **Disney-quality bar:** natural movement and reliability over feature complexity. Smooth motion interpolation is what avoids robotic-looking movement; polish and failure recovery matter more than an ambitious feature list.
- **Object-oriented, state-machine, configuration-driven design** — not quick scripts. This is a deliberate professional-practices signal for the portfolio.
- **Preserve working systems while enabling new capability** — the Pi migration deliberately keeps existing calibration and architecture intact rather than rewriting from scratch.
- **Safety-first:** torque limits, emergency stops, safe pulse-width bounds on every servo.
- **Systematic development methodology:** characterization tools → calibration procedures → integration testing → feature enhancement, in that order.
- **Documentation in narrative style** — emphasize engineering process and problem-solving, not just final code (this matters for the portfolio's audience).

---

## Vision Tracking Behavior (Design Intent)

- Lock onto the **first person detected** in FOV
- Hold that lock and continue tracking that same person as they move
- Only release/switch the lock when that person leaves the frame — not simply because another person entered
- This logic has not yet been implemented; it's a Part 1 requirement for the vision node

---

## Open / Next Decisions

- Voice/audio synthesis integration — explored conceptually only, not yet architected
- Whether the Jetson↔Pi ROS 2 network runs over Ethernet, Wi-Fi, or a dedicated link — not yet decided
- RealSense model: D435 vs D435i vs D455 — not yet finalized (D455 has longer range/wider FOV if the mounting distance calls for it)

---

## What This Document Is For

This is a snapshot of decisions made in a planning conversation with Claude (chat) before migrating to Claude Code for implementation. It is not exhaustive of every detail discussed — if something needed for implementation isn't covered here, ask the user rather than assuming.
