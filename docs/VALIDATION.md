# Validation report — version 1.0.0

Date: 2026-10-18.

## Executed

- Python 3.12 compilation of all Python source files: passed.
- `python -m unittest discover -s tests -v`: 19 tests passed.
- HTTP requests were sent to a running local receiver bound to loopback on an ephemeral port, with temporary SQLite databases.
- Validation includes duplicate request retry, old queued sample age, authentication rejection, invalid values, oversize bodies, CSV and concurrent storage.
- ZIP content check: source, firmware example, instructions and tests included; runtime databases, credentials, caches and virtual environments excluded.

## Not executed

- Desktop visual rendering: no graphical display service was available in the build environment. The Tkinter screen must be checked locally with the acceptance steps in the manual.
- Native Windows/PyCharm execution: not performed in this environment.
- ESP32 Arduino compilation, upload and physical sensor readings: not performed; require the actual board and installed sensor libraries.
- Physical pump/valve operation: not part of this version.

The illustration used as visual inspiration is not a screenshot of this software. No claim of agricultural field validation is made.
