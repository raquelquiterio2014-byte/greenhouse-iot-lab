# Local HTTP API — V3

Private trusted LAN prototype, one registered device (`greenhouse-01`), JSON body <=4096 bytes. No physical actuator API. Except `/health`, all routes require `Authorization: Bearer <local token>`. No token is included in reports or logs. HTTP is unencrypted.

| Method | Route | Meaning |
|---|---|---|
| GET | `/health` | Receiver process health, version and no-actuation flag |
| GET | `/api/status?source=real` | Authenticated transport/measurement diagnostics |
| GET | `/api/status?source=test` | Isolated synthetic transport diagnostics |
| POST | `/api/readings` | V1/V2-compatible measurement schema, physical input source |
| POST | `/api/test/readings` | Same measurement schema, source forced to synthetic `test` |
| POST | `/api/heartbeat` | Physical device presence and sensor state; no measurement inserted |
| POST | `/api/test/heartbeat` | Synthetic device presence and state; no measurement inserted |

V3 preserves measurement `schema_version: 2`; transport additions are a separate optional object. The V2 raw ADC/voltage/light and calibration workflow remains intact.

```json
{
  "schema_version": 2,
  "device_id": "greenhouse-01",
  "sample_id": "unique-boot:1",
  "temperature": 24.8,
  "humidity": 62,
  "soil_raw": 2316,
  "soil_mv": 1800,
  "light_raw": 864,
  "adc_samples": 10,
  "sample_age_seconds": 0,
  "transport": {
    "boot_id": "unique-boot",
    "sequence": 1,
    "queue_depth": 1,
    "dropped_samples": 0,
    "uptime_ms": 2200,
    "firmware_version": "3.0.0"
  }
}
```

Example numbers illustrate format only. Heartbeat body is `{"device_id":"greenhouse-01","status":"ok","transport":{...}}`; status can be `ok` or `sensor_fault`.

Responses: 201 new accepted reading; 200 identical retry or heartbeat; 400 malformed/invalid data; 401 invalid token; 409 ID reused with different raw measurement content; 413 body size limit; 415 wrong content type; 503 local storage unavailable. An acknowledgement includes `accepted`, `duplicate`, `source`, `sample_id`. The sender must match ID and source before dropping its queue record.

The first accepted record keeps its estimated acquisition time, raw values and calibration snapshot. Retry age, arrival time, transport counters and calibration revisions do not overwrite that record. Calibration applies at arrival, not at acquisition on the device; raw ADC permits future explicit reprocessing without silently rewriting old records.

Measurement time is estimated as receiver time minus supplied sample age. There is no synchronized hardware clock or cryptographic measurement attestation. A heartbeat can keep contact ACTIVE while the last measurement is STALE; an old queued observation cannot replace a newer one in the dashboard.

Transport logs persist accepted/duplicate/conflict/rejected/unauthorized/heartbeat/fault outcomes. They are not a complete network packet capture, guaranteed audit trail, or remotely verified queue inventory. They grow locally; routine backup/retention is an operator concern in this educational version.
