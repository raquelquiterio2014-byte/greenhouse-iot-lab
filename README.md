# Greenhouse IoT Lab V5 — Integrated monitoring and evaluation

Educational Python desktop greenhouse monitoring with calibrated observations, HTTP connectivity tests and snapshot-based trend screening. English interface; Portuguese setup guides. V4 adds an optional Gemini evidence-review adapter while preserving the deterministic measurement-quality gate.

## Start in PyCharm

1. Extract the ZIP into a NEW folder and open the folder containing `main.py` in PyCharm.
2. Select Python with Tcl/Tk (software checks use Python 3.12).
3. Run `main.py`, open **AI analysis**.
4. Select **Rising heat**, leave the Gemini checkbox OFF, click **Analyze snapshot**.
5. Try **Stale readings** and see the report withhold analysis.

No pip packages, paid API or hardware are required for local execution. Step-by-step: [docs/V4_START_HERE_PT.md](docs/V4_START_HERE_PT.md).

## What V5 adds

Run `python run_v5_evaluation.py` for four isolated end-to-end scenarios.
Synthetic schema-v2 readings pass through the persistent outbox, loopback HTTP
receiver, calibration, SQLite and local analysis. The JSON report records
individual checks, delivery results, connectivity state and analysis evidence.
The evaluation uses temporary databases and never calls Gemini or controls hardware.

See the [V5 guide in Portuguese](docs/V5_START_HERE_PT.md).

## What V4 adds

- A 30-minute, at-most-500-record analysis window from one selected source, or separate in-memory synthetic examples.
- Quality gate: recent data, five valid samples, at least 20 seconds, consistent sensor provenance/calibration, no active sensor-fault heartbeat, no future/malformed/mixed input or major time gaps.
- Descriptive per-variable mean, min/max, change and ordinary-least-squares slope per minute.
- Heuristic last-reading jump check against the prior median/MAD, plus configured heat and relative-soil threshold flags. No trained anomaly model or predictive claim.
- Optional Gemini selects existing evidence IDs and verification-check templates. Strict output validation rejects invented IDs, arbitrary prose/actions, duplicate fields and missing limitations.
- The model cannot replace deterministic findings/status, change readings or authorize equipment operation. The complete local findings remain visible even if the model prioritizes only a subset.
- Explicit NOT_REQUESTED / BLOCKED / GEMINI / LOCAL_FALLBACK provenance. Offline screening is never presented as a live model response.
- Frozen observation/calibration snapshot, SHA-256 input digest, audit rows in SQLite, and JSON/text export.
- A worker thread keeps optional API requests outside Tkinter's refresh loop. No model calls happen automatically while charts update.

## Gemini: optional and explicitly selected

Use a session-only masked key in the new tab or configure `GEMINI_API_KEY`. `GEMINI_MODEL` or the editable model field selects the model; the historical project default is `gemini-2.5-flash`. Availability and access depend on your Google account and current model lifecycle. Check the official model/deprecation pages and select an available compatible model if necessary; no replacement model is silently chosen.

Only after the external-API checkbox and an explicit Analyze click does the adapter send a controlled aggregate summary to Google's endpoint. Raw device/sample IDs, calibration reference text, local tokens and key are excluded. The summary includes synthetic/physical-route label, statistics, predefined findings, permitted checks and required limitations. Keys are not saved in SQLite, reports, project files or Git. No `.env` parser is included.

The adapter uses REST `generateContent` with JSON response MIME/schema, a 12-second per-attempt timeout and at most two attempts for transient network/429/5xx failures. Missing key, API error, blocked/truncated/invalid output or unsupported selection produces a labelled local fallback. Actual provider availability, quota, cost and live responses were not verified in this delivery.

The AI role is deliberately constrained: evidence prioritization and selection of existing review checks, followed by locally rendered explanations. This is not free-form agronomic advice, a multi-agent system, disease detection or autonomous irrigation.

## Three observation sources, retained from V3

| Mode | Origin | Meaning |
|---|---|---|
| DEMO | `demo` | Direct synthetic monitoring simulation |
| HTTP TEST | `test` | Synthetic device through real loopback HTTP and an isolated test route |
| LIVE ESP32 | `real` | Physical-input route; installation/measurement authenticity still needs operator validation |

V4 synthetic analysis examples are in-memory fixtures and do not add observations to LIVE or HTTP TEST history. Their saved analysis reports are explicitly labelled `synthetic_case`. The quality gate is still applied to them.

Sensors: DHT22 / AM2302 (air temperature and relative humidity), DFRobot SEN0193 (relative calibrated soil index, NOT VWC) and BH1750 (illuminance, NOT PAR/PPFD). Hardware/units/calibration details: [docs/MANUAL_PT.md](docs/MANUAL_PT.md), [docs/SENSOR_SELECTION.csv](docs/SENSOR_SELECTION.csv).

## Retained connectivity and firmware

V3 receiver, bounded outbox, acknowledgements, deduplication, heartbeat/sensor-fault reporting and source isolation remain. See [docs/V3_START_HERE_PT.md](docs/V3_START_HERE_PT.md) and [docs/API_V3.md](docs/API_V3.md). The sketch remains firmware 3.0.0; no new hardware or physical actuator driver is needed for V4's analysis layer. Receiver process reports application version 5.0.0.

## Audit, scope and validation

- 78 software tests passed: 54 regression tests plus 24 analysis/gateway/audit tests.
- Gemini tests use controlled mock responses. No live Gemini request or successful real-model output is claimed.
- Windows GUI visual validation, Arduino compilation, physical sensor deployment, field accuracy and agricultural validation are pending.
- Existing V1–V3 observation data is preserved. `analysis_runs` is added without rewriting observations or old calibration snapshots.
- Audit digests identify a snapshot, not a digital signature or tamper-proof database.
- No physical pump or valve control. Every report says `NO_ACTION_AUTHORIZED`.

Run tests/report:

```console
python run_v4_checks.py
```

Headless example:

```console
python analyze_snapshot.py --example "Rising heat"
```

Explicit cloud request after setting environment key/model:

```console
python analyze_snapshot.py --example "Rising heat" --gemini
```

Report and sample results: [docs/VALIDATION.md](docs/VALIDATION.md). Runtime `data/`, `exports/`, `.env` files and firmware `secrets.h` are ignored by Git. If uploading manually, exclude them yourself. Keep the private-LAN HTTP receiver off the public internet.

## Five-version roadmap

V1 dashboard/simulation → V2 sensors/calibration → V3 connectivity → **V4 trends and optional AI review** → **V5 integrated evaluation**.

## Primary API references

- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash
- https://ai.google.dev/gemini-api/docs/deprecations

MIT license retained from the existing repository. Version 5.0.0.
