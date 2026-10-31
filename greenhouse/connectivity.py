"""Transport validation and status. Never equate contact with fresh sensor data."""
from datetime import datetime, timezone
import json
import math

TRANSPORT_FIELDS = {'boot_id','sequence','queue_depth','dropped_samples','uptime_ms','firmware_version'}


def validate_transport(value):
    if value is None:return {}
    if not isinstance(value,dict) or set(value)-TRANSPORT_FIELDS:
        raise ValueError('Unknown transport fields')
    out={}
    for key,item in value.items():
        if key in ('boot_id','firmware_version'):
            if not isinstance(item,str) or not 1<=len(item)<=96 or not all(c.isalnum() or c in '._:-' for c in item):
                raise ValueError(f'Invalid {key}')
        elif type(item) is not int or not 0<=item<=4294967295:
            raise ValueError(f'{key} must be an unsigned 32-bit integer')
        if key=='queue_depth' and item>32:raise ValueError('queue_depth exceeds 32-slot firmware queue')
        out[key]=item
    return out


def seconds_since(timestamp, now=None):
    if timestamp is None:return None
    now=now or datetime.now(timezone.utc)
    return max(0,(now-datetime.fromisoformat(timestamp)).total_seconds())


def summarize(store,source,stale_seconds=180,contact_seconds=90,now=None):
    if source not in ('real','test'):raise ValueError('Status source must be real or test')
    rows=store.recent(source,1)
    row=rows[-1] if rows else None
    with store.connect() as db:
        counters={r['outcome']:r['n'] for r in db.execute(
            'SELECT outcome,COUNT(*) n FROM transport_log WHERE source=? GROUP BY outcome',(source,))}
        contact=db.execute("SELECT * FROM transport_log WHERE source=? AND outcome IN ('accepted','duplicate','heartbeat','sensor_fault') ORDER BY id DESC LIMIT 1",(source,)).fetchone()
        heartbeat=db.execute("SELECT * FROM transport_log WHERE source=? AND outcome IN ('heartbeat','sensor_fault') ORDER BY id DESC LIMIT 1",(source,)).fetchone()
    contact_age=seconds_since(contact['created_at'],now) if contact else None
    measured_age=seconds_since(row['measured_at'],now) if row else None
    return dict(source=source,kind='physical' if source=='real' else 'synthetic_http_test',
        contact_state='WAITING' if contact_age is None else ('ACTIVE' if contact_age<=contact_seconds else 'SILENT'),
        contact_age_seconds=contact_age,
        measurement_state='NO_DATA' if row is None else ('STALE' if measured_age>stale_seconds else 'FRESH'),
        measurement_age_seconds=measured_age,last_measured_at=row['measured_at'] if row else None,
        latest_quality=row['quality'] if row else None,counts=counters,
        last_device_status=contact['outcome'] if contact else None,
        sensor_status=('FAULT' if heartbeat['outcome']=='sensor_fault' else 'OK') if heartbeat else 'UNKNOWN',
        transport=json.loads(contact['metadata']) if contact else {},
        stored_samples=store.count(source),hardware_validation='PENDING')
