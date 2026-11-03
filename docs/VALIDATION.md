# V4 validation report

Date: 2026-11-03. Python 3.12.

## Executed

- Python compilation and desktop-module import checks.
- 78 automated tests: 54 V1–V3 regression checks and 24 V4 quality, statistics, provider-contract and audit tests.
- Synthetic normal/heat/dry/spike/stale/uncalibrated/saturation scenarios.
- Gates for source mixing, missing provenance, numeric/range errors, future/duplicate timestamps, sampling gaps and sensor-fault heartbeats.
- Exact descriptive-slope fixture and configured-limit signals; immutable observation/calibration snapshot and audit storage.
- Gemini mocked valid/malformed/truncated/error responses, bounded 429 retries, no retry for auth failure, missing key and explicit local fallback.
- Model selection cannot invent evidence/actuator commands, omit mandatory limitations or replace deterministic findings and authorization.
- Loopback HTTP and persistent-queue regression tests remain passing.
- Headless analysis CLI and test-report entry point checked.

## Not executed / not claimed

- Live Gemini API request, provider account access, quota, billing or agronomic quality of model selections.
- Native Windows/PyCharm visual layout.
- ESP32 compilation, physical sensor installation, field calibration or agricultural operating validation.
- Any physical actuator operation. Firmware remains V3; no new hardware driver is introduced.

Local screening is a documented heuristic, not a trained predictive/anomaly model. Provider tests use mocks and temporary databases. Hardware validation remains PENDING. Every report retains NO_ACTION_AUTHORIZED.
