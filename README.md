# Greenhouse IoT Lab

A Python desktop greenhouse dashboard for PyCharm, inspired by the four readings in the IoT architecture illustration. English interface; complete Portuguese setup guide in [docs/MANUAL_PT.md](docs/MANUAL_PT.md).

## Start in PyCharm

1. Extract the ZIP into a normal folder, for example `C:\Users\Master\PycharmProjects\Greenhouse_IoT_Lab`.
2. Open that folder in PyCharm.
3. Select a Python interpreter with Tcl/Tk. Development checks ran on Python 3.12; the code uses only the standard library.
4. Open **main.py**, then click **Run**.

There are no pip dependencies, cloud accounts, model APIs or subscriptions. Windows Python normally includes Tkinter; on Linux install your distribution's Tkinter package if needed.

```console
python main.py
```

## What it does

- Four value cards with actual time axes: air temperature, air humidity, soil moisture, light intensity.
- Initial DEMO values: 24.8 °C, 62%, 38%, 720 lux. Subsequent readings change.
- Normal, Dry soil, Hot day and Night demonstration scenarios; sampling every two seconds.
- Simulated irrigation with hysteresis, manual stop, maximum run time and stale-data handling.
- LIVE ESP32 mode only displays received sensor measurements; it never falls back to demo values.
- Local HTTP receiver with bearer token, finite-number/range validation, body-size limit and duplicate detection.
- SQLite history and event log. Demo and real histories are queried separately.
- Export all readings for the selected mode to CSV, including provenance, timestamps and sample ID.
- Classic ESP32 DevKit firmware for DHT22, capacitive soil sensor and BH1750.
- Firmware samples every 60 seconds. A bounded RAM queue retains up to 32 readings while the PC/network is unavailable. Retry occurs every five seconds; oldest sample is dropped if full. RAM queue does not survive a reset.

## What it does not do

This is a local monitoring/teaching project. No physical relay, valve or pump is controlled. Demo irrigation is a simulation. Crop-specific thresholds and soil calibration must be established for the actual installation. No remote cloud dashboard, MQTT broker, AI model or production deployment is included.

The soil percentage is a relative dry/wet sensor calibration, not laboratory volumetric water content. Light is measured in lux by BH1750; lux does not directly measure plant PPFD/PAR.

## Connect physical sensors

Follow [the Portuguese manual](docs/MANUAL_PT.md). The included Arduino sketch and wiring target a **classic ESP32 DevKit**. ESP32-C3/S3 pin assignments differ.

In the app: **IoT connection & settings** → host `0.0.0.0` → **Save settings** → **Start receiver**. Put the PC LAN address and app token into your local firmware `secrets.h`. Switch to **LIVE ESP32**.

Receiver default: `127.0.0.1:8765`. `GET /health` checks receiver availability. `POST /api/readings` accepts the JSON payload documented in the manual. HTTP is intended for a trusted private LAN; it is not encrypted and must not be exposed through internet port forwarding.

## Local files and GitHub

Runtime files are created inside `data/` automatically, relative to this project, independent of PyCharm's working directory. `data/greenhouse.sqlite3` contains history, and `data/settings.json` contains the locally generated token. Both `data/` and firmware `secrets.h` are ignored by Git.

Back up the SQLite file with the app closed. On GitHub upload the source, docs, tests and example secrets file. Do not upload local credentials or a populated runtime `data/` folder.

## Tests

From the project root:

```console
python -m unittest discover -s tests -v
```

19 automated tests cover malformed/non-finite sensor values, stale readings, deduplication, source separation, late backfill ordering, concurrent storage, complete CSV export, scenarios, control rules and authenticated HTTP ingestion. These tests use temporary databases and do not put fake measurements into your live history.

See [docs/VALIDATION.md](docs/VALIDATION.md) for precise validation scope. Desktop rendering and physical hardware operation require local validation; this package does not claim a Windows GUI or hardware test.

## Architecture

| Layer | Implementation |
|---|---|
| Perception | ESP32, DHT22, capacitive soil sensor, BH1750; separate demo generator |
| Network | Local Wi-Fi + HTTP JSON, token, RAM retry queue |
| Processing | Python validation, SQLite, monitoring thresholds; simulated irrigation rules |
| Application | Tkinter charts, alerts, history, CSV export |

## Primary technical references

- Espressif Arduino-ESP32 HTTP example: https://github.com/espressif/arduino-esp32/tree/master/libraries/HTTPClient/examples/BasicHttpClient
- Adafruit DHT sensor library: https://github.com/adafruit/DHT-sensor-library
- BH1750 library by claws: https://github.com/claws/BH1750

MIT licensed. Version 1.0.0.
