"""Validated observations, local SQLite history and deterministic demo rules."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv
import math
import random
import re
import sqlite3
import time
import uuid
from .sensors import Calibration, DEMO_CALIBRATION, BH1750_MAX_LUX, finite, soil_usable

RANGES = {'temperature': (-40, 80), 'humidity': (0, 100),
          'soil_moisture': (0, 100), 'light_lux': (0, BH1750_MAX_LUX)}


def utcnow():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Reading:
    source: str
    device_id: str
    sample_id: str
    measured_at: str
    received_at: str
    temperature: float
    humidity: float
    soil_moisture: float
    light_lux: float

    # All fields below preserve measurement provenance; V1 rows migrate as legacy.
    soil_raw: float | None = None
    soil_mv: float | None = None
    soil_unclamped: float | None = None
    light_raw: int | None = None
    temperature_raw: float | None = None
    humidity_raw: float | None = None
    adc_samples: int | None = None
    calibration_id: str = 'legacy'
    calibration_snapshot: str = '{}'
    quality: str = 'LEGACY_NO_RAW'
    schema_version: int = 1

    @classmethod
    def from_payload(cls, payload, source='real', device='greenhouse-01', calibration=None):
        if not isinstance(payload, dict):
            raise ValueError('JSON must be an object')
        version=payload.get('schema_version',1)
        if type(version) is not int or version not in (1,2):
            raise ValueError('schema_version must be 1 or 2')
        fields=set(RANGES) if version==1 else {'temperature','humidity','soil_raw','soil_mv','light_raw','adc_samples'}
        allowed=fields | {'device_id','sample_id','sample_age_seconds','schema_version'}
        if set(payload)-allowed:raise ValueError('Unexpected fields: '+', '.join(sorted(set(payload)-allowed)))
        if payload.get('device_id')!=device:raise ValueError('Device ID does not match this greenhouse')
        sid=payload.get('sample_id')
        if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,96}',sid):
            raise ValueError('sample_id must contain 1-96 letters, digits or ._:-')
        age=finite(payload.get('sample_age_seconds',0),'sample_age_seconds')
        if not 0<=age<=86400:raise ValueError('sample_age_seconds must be between 0 and 86400')
        now=utcnow(); extras={}
        if version==1:
            values={k:finite(payload.get(k),k) for k in RANGES}
            for k,(low,high) in RANGES.items():
                if not low<=values[k]<=high:raise ValueError(f'{k} outside selected sensor range')
        else:
            cal=(calibration or Calibration()).validate()
            raw_t=finite(payload.get('temperature'),'temperature')
            raw_h=finite(payload.get('humidity'),'humidity')
            raw=finite(payload.get('soil_raw'),'soil_raw')
            mv=finite(payload.get('soil_mv'),'soil_mv')
            light=payload.get('light_raw');count=payload.get('adc_samples')
            if not -40<=raw_t<=80 or not 0<=raw_h<=100:raise ValueError('DHT22 outside measurement range')
            if not 0<=raw<=4095 or not 0<=mv<=3300:raise ValueError('Soil ADC or measured voltage outside input range')
            if type(light) is not int or not 0<=light<=65535:raise ValueError('light_raw must be 16-bit integer')
            if count!=10 or type(count) is not int:raise ValueError('V2 firmware must average 10 ADC samples')
            soil,unclamped,flags=cal.soil_index(raw)
            if light==65535:flags.append('LIGHT_SATURATED')
            t=raw_t+cal.temperature_offset;h=raw_h+cal.humidity_offset
            if not -40<=t<=80 or not 0<=h<=100:raise ValueError('Corrected DHT22 value outside range; review offsets')
            values=dict(temperature=round(t,1),humidity=round(h,1),soil_moisture=soil,light_lux=light/1.2)
            extras=dict(soil_raw=raw,soil_mv=mv,soil_unclamped=unclamped,light_raw=light,
                temperature_raw=raw_t,humidity_raw=raw_h,adc_samples=count,calibration_id=cal.revision,
                calibration_snapshot=cal.snapshot(),quality=';'.join(flags) or 'OK',schema_version=2)
        return cls(source,device,sid,(now-timedelta(seconds=age)).isoformat(),now.isoformat(),**values,**extras)

    def age(self):
        return max(0, (utcnow()-datetime.fromisoformat(self.measured_at)).total_seconds())


class Store:
    """Each operation opens its own connection, safe across UI and HTTP threads."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, device_id TEXT NOT NULL,
                sample_id TEXT NOT NULL, measured_at TEXT NOT NULL, received_at TEXT NOT NULL,
                temperature REAL, humidity REAL, soil_moisture REAL, light_lux REAL,
                UNIQUE(source, device_id, sample_id))''')
            existing={row['name'] for row in db.execute('PRAGMA table_info(readings)')}
            extra_columns={'soil_raw':'REAL','soil_mv':'REAL','soil_unclamped':'REAL','light_raw':'INTEGER',
                'temperature_raw':'REAL','humidity_raw':'REAL','adc_samples':'INTEGER',
                'calibration_id':"TEXT DEFAULT 'legacy'",'calibration_snapshot':"TEXT DEFAULT '{}'",
                'quality':"TEXT DEFAULT 'LEGACY_NO_RAW'",'schema_version':'INTEGER DEFAULT 1'}
            for name,kind in extra_columns.items():
                if name not in existing:db.execute(f'ALTER TABLE readings ADD COLUMN {name} {kind}')
            db.execute('CREATE INDEX IF NOT EXISTS idx_readings_source_time ON readings(source, measured_at)')
            db.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, created_at TEXT, source TEXT, message TEXT)''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def add(self, reading):
        fields = asdict(reading)
        with self.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO readings (' + ','.join(fields) +
                             ') VALUES (' + ','.join('?' for _ in fields) + ')', tuple(fields.values()))
            return bool(cur.rowcount)

    def recent(self, source, limit=120):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM readings WHERE source=? ORDER BY measured_at DESC, id DESC LIMIT ?',
                              (source, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def count(self, source):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM readings WHERE source=?', (source,)).fetchone()[0]

    def event(self, source, message):
        with self.connect() as db:
            db.execute('INSERT INTO events(created_at,source,message) VALUES (?,?,?)',
                       (utcnow().isoformat(), source, message))

    def events(self, source, limit=25):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events WHERE source=? ORDER BY id DESC LIMIT ?',
                                               (source, limit)).fetchall()]

    def export(self, source, filename):
        # Stream the complete history, not just the last chart window.
        with self.connect() as db, open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            cursor = db.execute('SELECT * FROM readings WHERE source=? ORDER BY measured_at,id', (source,))
            writer = csv.writer(f)
            writer.writerow([col[0] for col in cursor.description])
            writer.writerows(cursor)


class Simulator:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.values = [24.8, 62., 38., 720.]
        self.scenario = 'Normal'
        self.boot = uuid.uuid4().hex[:10]
        self.seq = 0

    def set_scenario(self, name):
        self.scenario = name
        self.values = {'Normal': [24.8, 62., 38., 720.], 'Dry soil': [27., 48., 27., 980.],
                       'Hot day': [39.5, 38., 43., 1600.], 'Night': [19., 75., 48., 4.], 'Light saturation': [30.,55.,40.,BH1750_MAX_LUX]}[name][:]

    def sample(self, irrigating=False, advance=True):
        if advance:
            limits = [(-10, 55), (5, 99), (1, 99), (0, 10000)]
            steps = [.13, .4, (-.15 if not irrigating else 2.5), 14.]
            for i in range(4):
                delta = steps[i] if i == 2 else self.rng.uniform(-steps[i], steps[i])
                if i == 3 and self.scenario == 'Night':
                    delta = self.rng.uniform(-2, 2)
                self.values[i] = round(max(limits[i][0], min(limits[i][1], self.values[i] + delta)), 2)
        self.seq += 1
        t,h,soil,lux=self.values
        raw=3000-soil*18
        light=65535 if self.scenario=='Light saturation' else min(65534,round(lux*1.2))
        return Reading.from_payload(dict(device_id='greenhouse-01',sample_id=f'{self.boot}:{self.seq}',
            schema_version=2,temperature=t,humidity=h,soil_raw=raw,
            soil_mv=raw/4095*3300,light_raw=light,adc_samples=10),
            source='demo',calibration=DEMO_CALIBRATION)



class Irrigation:
    """Simulated actuator only. No GPIO commands or hardware endpoint."""
    def __init__(self):
        self.active = False
        self.automatic = True
        self.deadline = 0.
        self.locked = False

    def stop(self):
        self.active = False

    def start(self, now=None, duration=10):
        self.active = True
        self.deadline = (time.monotonic() if now is None else now) + duration

    def update(self, soil, fresh=True, now=None):
        now = time.monotonic() if now is None else now
        if not fresh:
            self.active = False
            return 'No fresh sample - simulated irrigation stopped'
        if soil >= 45:
            self.locked = False
        if self.active and (soil >= 45 or now >= self.deadline):
            timeout = now >= self.deadline and soil < 45
            self.active = False
            self.locked = timeout
            return 'Simulation stopped: maximum time' if timeout else 'Simulation stopped: soil target reached'
        if not self.active and self.automatic and not self.locked and soil < 35:
            self.start(now, 20)
            return 'Dry soil - simulated irrigation started (maximum 20 s)'
        return None


def alerts(reading, stale_seconds=180, temperature_high=38., soil_low=35.):
    if reading is None:
        return ['Waiting for measurements']
    if reading.age() > stale_seconds:
        return ['STALE DATA - check device, power and local network']
    out = []
    if reading.temperature > temperature_high:
        out.append(f'High air temperature: {reading.temperature:.1f} °C')
    if soil_usable(reading) and reading.soil_moisture < soil_low:
        out.append(f'Dry soil: {reading.soil_moisture:.1f}%')
    if reading.quality != 'OK':
        out.append('Measurement quality: '+reading.quality+' - review Sensors & calibration')
    return out or ['All monitored thresholds are normal']
