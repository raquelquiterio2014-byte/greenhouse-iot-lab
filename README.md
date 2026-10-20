# Greenhouse IoT Lab V2 — Sensor selection and calibrated measurements

Python/Tkinter greenhouse monitoring dashboard for PyCharm. English interface, Portuguese manual. Based on EmpreendAIoT Units 2–3: choose the physical quantity first, verify the sensor datasheet, calibrate, filter and install correctly.

## Run

Extract all files. Open the folder containing `main.py` in PyCharm and run `main.py` with Python 3.12 and Tcl/Tk. No pip packages or paid services are needed for the desktop application.

```console
python main.py
```

## Selected sensors

| Quantity on the dashboard | Sensor | Interface / classic ESP32 pin | Meaning |
|---|---|---|---|
| Air temperature, °C | DHT22 / AM2302 | Digital proprietary protocol, GPIO 4 | Air only; 0.1 °C output resolution does not mean ±0.1 °C accuracy |
| Air relative humidity, % RH | Same DHT22 | Same GPIO 4 | Not soil moisture; protect from condensation |
| Relative soil moisture index, % relative | DFRobot SEN0193 | Analog AO, GPIO 34 ADC1 | Two-point local scale; NOT volumetric water content |
| Illuminance, lux | BH1750FVI compatible 3.3 V module | I2C, SDA 21 / SCL 22 / address 0x23 | Lux, NOT PAR, PPFD or direct photosynthesis measurement |

SEN0193 is the documented reference product; generic capacitive v1.2 boards are not assumed electrically identical. Verify the purchased board and calibrate it individually. We did not add all sensors from the course catalogue: PIR, MQ, current sensing and pressure are not required for these four measurements.

## What's new in V2

- **Sensors & calibration** tab: model, quantity, units, interface, operating range, accuracy/resolution, sampling and installation rationale.
- Calibrate the installed soil probe using measured dry/wet ADC references, plus optional independent DHT22 temperature/humidity reference offsets.
- Live soil is marked unavailable until calibration is confirmed. Example endpoints are never presented as real calibration.
- V2 firmware averages **10 soil ADC readings** and separately averages calibrated `analogReadMilliVolts()` conversions.
- Raw ADC, measured mV, raw light, raw/corrected DHT values, quality, calibration revision and immutable calibration snapshot are stored/exported.
- Out-of-reference soil, ADC rails and BH1750 saturation are flagged; the affected latest chart/card is withheld instead of presenting it as a reliable measurement.
- SQLite V1 databases migrate additively. Old rows remain explicitly `LEGACY_NO_RAW` and are never recalibrated in place.
- V1 HTTP payloads remain accepted inside tightened ranges, but soil is not treated as calibrated. Update the firmware for the full V2 workflow.
- Separate real and synthetic calibration, histories and scenarios. New **Light saturation** demo scenario.

## BH1750 range correction

V1's generic 200,000-lux limit was inappropriate for this fixed sensor mode. V2 fixes **H-resolution / MTreg 69** and computes `lux = raw16 / 1.2`. The numerical maximum is **54,612.5 lux**; raw 65,535 is flagged `LIGHT_SATURATED`. The course/datasheet headline mentions a wider nominal range and adjustable modes; this code does not silently switch modes or claim unlimited sunlight measurement. A zero reading is valid in darkness.

## Calibration and installation

Full instructions: [docs/MANUAL_PT.md](docs/MANUAL_PT.md).

The course's generic 1.5 m air-sensor mounting example must be adapted to representative canopy height in a greenhouse. The soil-sensor depth must match the root zone AND the probe's sensing-blade length; a generic 15 cm example is not an instruction to bury unprotected electronics. Put BH1750 above the canopy with upward-facing unobstructed sensing surface; check any optical window influence.

DHT22 humidity figures vary with conditions: the cited sheet gives typical ±2 percentage points RH, maximum ±5. Correcting an offset or taking a mean does not certify precision. The ±5-point tolerance in a course exercise is a design requirement, not proven SEN0193 accuracy.

## Data flow

ESP32 physical readings → local Wi-Fi / HTTP JSON → validation → calibration / quality → SQLite → Tkinter dashboard / CSV.

No internet is required when local Wi-Fi and the receiver computer remain available. The ESP32 retains a bounded 32-sample RAM queue while the link/receiver is unavailable; power loss clears it, and overflow drops the oldest record. `sample_age_seconds` keeps backfill from being mistaken for new data.

The local bearer-token HTTP service is for a trusted private LAN. It is not encrypted; do not publish the receiver directly to the internet. Configuration is in the GUI; secrets remain in ignored local files.

## Actuators

Irrigation is still simulated with hysteresis and a maximum run time. A relay and normally closed 12 V valve appear only as a future component specification. No physical GPIO, pump, valve, mains or fan driver is implemented. Choosing a relay contact rating is not equivalent to validating a load/inrush/protection design.

## Test and validation

```console
python -m unittest discover -s tests -v
```

See [docs/VALIDATION.md](docs/VALIDATION.md) for executed checks and limitations. This package does not claim Windows rendering, ESP32 compilation, field calibration or physical installation testing.

## Main files

- `main.py`: PyCharm entry point.
- `greenhouse/app.py`: dashboard, history and receiver settings.
- `greenhouse/sensor_panel.py`: specification and calibration UI.
- `greenhouse/sensors.py`: catalogue, conversion and calibration registry.
- `greenhouse/core.py`: observations, SQLite migration, demo and rules.
- `greenhouse/receiver.py`: authenticated local HTTP receiver.
- `firmware/greenhouse_esp32/`: V2 sketch and example secrets.
- `tests/`: automated regression and measurement tests.

Runtime `data/`, credentials and `secrets.h` are excluded by `.gitignore`. If uploading manually on GitHub, exclude them yourself. Back up a V1 database with the app closed before using V2. Open a new folder for V2; copy old data only if you deliberately want to migrate it.

## References

- User-supplied EmpreendAIoT Unit 3, *Sensores e atuadores*: lessons 1–12 and accompanying text. Course files are not redistributed.
- DHT22 manufacturer's sheet: https://cdn.sparkfun.com/assets/f/7/d/9/c/DHT22.pdf
- DFRobot SEN0193: https://wiki.dfrobot.com/sen0193/
- ROHM BH1750FVI Rev.D sheet: https://www.mouser.com/datasheet/2/348/bh1750fvi-e-186247.pdf
- Espressif Arduino ADC: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html
- Arduino libraries: https://github.com/adafruit/DHT-sensor-library and https://github.com/claws/BH1750

MIT license. Version 2.0.0.
