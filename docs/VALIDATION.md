# V3 validation report

Date: 2026-10-31. Python 3.12.

## Executed software checks

- Python modules compile and desktop modules import without syntax/import errors.
- 54 tests pass: all 33 V1/V2 regression checks plus 21 V3 transport/outbox checks.
- V3 integration tests start a real loopback HTTP receiver with temporary SQLite files.
- Tested source separation, receiver stop/restart, simulated acknowledgement loss, identical retries, ID-content conflicts, invalid token/metadata, heartbeat-only contact, backfill age, sensor-fault indication and authenticated status reports.
- Tested persistent synthetic queue, capacity/drop accounting, retry backoff, invalid acknowledgements, permanent rejections, explicit offline pause and expired entries.
- CSV preserves transport metadata in addition to existing raw/calibrated values.
- `run_v3_checks.py` creates a machine-readable software test report with explicit hardware limitations.

## Pending

- Visual rendering on Windows/PyCharm. No GUI display service is available in this environment; desktop modules were imported, not visually validated.
- Arduino toolchain compilation/upload and ESP32 physical execution.
- Sensor wiring, installation, field calibration, actual Wi-Fi disconnect/reconnect and physical sensor-fault responses.
- Physical pump/valve actuation is not implemented.

The persistent outbox tests apply to the Python synthetic device, not to ESP32 flash storage. The physical firmware queue is RAM-only. Connection contact does not prove fresh measurements or agricultural suitability. No cloud, MQTT or AI integration is part of V3.

Manual acceptance steps: `docs/V3_START_HERE_PT.md`. Record physical evidence in `docs/HARDWARE_VALIDATION.csv`; do not mark physical checks complete based only on software tests.
