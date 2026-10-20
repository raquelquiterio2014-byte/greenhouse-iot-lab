# V2 validation report

Date: 2026-10-20. Runtime: Python 3.12.

## Executed

- All Python modules compiled/imported without syntax errors.
- `python -m unittest discover -s tests -v`: **33 tests passed**, including the 19 V1 regression tests.
- Added checks for calibrated index, raw/corrected value separation, DHT offsets, invalid and reversed endpoints, unconfirmed references, out-of-reference index, ADC rails, BH1750 saturation, actual mode limits, filter/ADC teaching math, schema/type rejection, immutable calibration revisions, JSON registry round-trip, CSV provenance and V1 SQLite migration.
- V2 integration requests ran against an actual loopback HTTP listener backed by a temporary SQLite database, including calibration changes between duplicate retries.
- Package excludes local databases, tokens, firmware secrets, virtual environments and caches.

## Not executed

- Native Windows/PyCharm execution and visual desktop rendering: no graphical display was available here. Follow local acceptance steps in MANUAL_PT.md.
- Arduino compilation, physical ESP32 upload, wiring and calibration: need the actual board, toolchain and sensor libraries.
- Agricultural field accuracy, traceable metrology and actuator operation: not claimed. Physical actuation is not part of this version.

## Important interpretation

`OK` means implemented validation checks passed; it does not certify accuracy or prove installation quality. Voltage is reported from the ESP32 API; it was not measured against a laboratory reference in this delivery. A calibration acknowledgement is entered by the operator, not independently verified by software.
