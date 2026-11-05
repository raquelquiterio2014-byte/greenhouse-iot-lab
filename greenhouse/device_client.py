"""Persistent synthetic HTTP device. Its URL is restricted to the loopback test route."""
from __future__ import annotations
from contextlib import closing, contextmanager
import json
from pathlib import Path
import random
import sqlite3
import threading
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from .core import Simulator


class Outbox:
    def __init__(self,path,capacity=32):
        if not 1<=capacity<=32:raise ValueError('Queue capacity must be 1..32')
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.capacity=capacity
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,sample_id TEXT UNIQUE,payload TEXT,created_at REAL,attempts INTEGER DEFAULT 0,next_retry REAL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER)')
            db.execute("INSERT OR IGNORE INTO meta VALUES('dropped',0)")
            db.execute('CREATE TABLE IF NOT EXISTS rejected(id INTEGER PRIMARY KEY,sample_id TEXT,reason TEXT,created_at REAL)')

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def enqueue(self,payload,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # A repeated enqueue must not evict an unrelated sample.
            if db.execute('SELECT 1 FROM outbox WHERE sample_id=?',(payload['sample_id'],)).fetchone():return
            if db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]>=self.capacity:
                db.execute('DELETE FROM outbox WHERE id=(SELECT id FROM outbox ORDER BY id LIMIT 1)')
                db.execute("UPDATE meta SET value=value+1 WHERE key='dropped'")
            db.execute('INSERT INTO outbox(sample_id,payload,created_at) VALUES(?,?,?)',
                       (payload['sample_id'],json.dumps(payload),now))

    def head(self):
        with self.connect() as db:
            row=db.execute('SELECT * FROM outbox ORDER BY id LIMIT 1').fetchone()
            return dict(row) if row else None

    def count(self):
        with self.connect() as db:return db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]

    def dropped(self):
        with self.connect() as db:return db.execute("SELECT value FROM meta WHERE key='dropped'").fetchone()[0]

    def reject(self,row,reason):
        with self.connect() as db:
            db.execute('INSERT INTO rejected(sample_id,reason,created_at) VALUES(?,?,?)',(row['sample_id'],reason,time.time()))
            db.execute('DELETE FROM outbox WHERE id=?',(row['id'],))

    def acknowledge(self,row):
        with self.connect() as db:db.execute('DELETE FROM outbox WHERE id=?',(row['id'],))

    def defer(self,row,now,delay):
        with self.connect() as db:
            db.execute('UPDATE outbox SET attempts=attempts+1,next_retry=? WHERE id=?',(now+delay,row['id']))


def post_json(url,token,payload):
    req=Request(url,data=json.dumps(payload,allow_nan=False).encode(),headers={
        'Content-Type':'application/json','Authorization':'Bearer '+token})
    try:
        with urlopen(req,timeout=1) as r:return r.status,json.loads(r.read())
    except HTTPError as exc:
        try:body=json.loads(exc.read())
        except (ValueError,UnicodeDecodeError):body={}
        return exc.code,body
    except (OSError,ValueError,URLError):return 0,{'error':'No valid HTTP response'}


class DeviceClient:
    def __init__(self,url,token,outbox,interval=2,sender=post_json):
        parsed=urlsplit(url)
        if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or
                parsed.path!='/api/test/readings' or parsed.query or parsed.fragment or parsed.username):
            raise ValueError('Synthetic client requires http://127.0.0.1:PORT/api/test/readings')
        if interval<.1:raise ValueError('Sample interval must be at least 0.1 s')
        self.url,self.token,self.outbox,self.interval,self.sender=url,token,outbox,interval,sender
        self.heartbeat_url=url.replace('/api/test/readings','/api/test/heartbeat')
        self.sim=Simulator();self.offline=False;self.pause_sampling=False
        self.last_sample=0.;self.last_heartbeat=0.;self.started=time.time()
        self.last_result='Not started';self.sent=0;self.failures=0;self.rejected=0
        self.stop_event=threading.Event();self.thread=None
        self.rng=random.Random()

    def sample_payload(self):
        r=self.sim.sample()
        return dict(schema_version=2,device_id=r.device_id,sample_id=r.sample_id,
            temperature=r.temperature_raw,humidity=r.humidity_raw,soil_raw=r.soil_raw,
            soil_mv=r.soil_mv,light_raw=r.light_raw,adc_samples=10,
            transport=dict(boot_id=self.sim.boot,sequence=self.sim.seq,firmware_version='3.0.0-simulator'))

    def metadata(self):
        return dict(queue_depth=self.outbox.count(),dropped_samples=self.outbox.dropped(),
                    uptime_ms=min(4294967295,int(max(0,time.time()-self.started)*1000)))

    def send_pending(self,now=None):
        now=time.time() if now is None else now
        if self.offline:return 'offline'
        row=self.outbox.head()
        if row is None:return 'empty'
        if now<row['next_retry']:return 'backoff'
        age=max(0,now-row['created_at'])
        if age>86400:
            self.outbox.reject(row,'Expired: older than one day');self.rejected+=1;return 'expired'
        payload=json.loads(row['payload']);payload['sample_age_seconds']=age
        payload['transport'].update(self.metadata())
        code,body=self.sender(self.url,self.token,payload)
        if not isinstance(body,dict):body={}
        if code in (200,201) and body.get('accepted') is True and body.get('sample_id')==row['sample_id'] and body.get('source')=='test':
            self.outbox.acknowledge(row);self.sent+=1
            self.last_result='Acknowledged duplicate' if body.get('duplicate') else 'Delivered to TEST history'
            return 'acknowledged'
        if code in (400,409,413,415):
            self.outbox.reject(row,f'HTTP {code}');self.rejected+=1;self.last_result=f'Rejected: HTTP {code}'
            return 'rejected'
        delay=30 if code in (401,403) else min(30,2**min(row['attempts'],5))+self.rng.uniform(0,.25)
        self.outbox.defer(row,now,delay);self.failures+=1;self.last_result=f'Retry pending (HTTP {code or "unavailable"})'
        return 'retry'

    def step(self,now=None):
        now=time.time() if now is None else now
        if not self.pause_sampling and now-self.last_sample>=self.interval:
            self.outbox.enqueue(self.sample_payload(),now);self.last_sample=now
        if not self.offline and now-self.last_heartbeat>=30:
            self.sender(self.heartbeat_url,self.token,dict(device_id='greenhouse-01',status='ok',
                transport=dict(boot_id=self.sim.boot,firmware_version='3.0.0-simulator',**self.metadata())))
            self.last_heartbeat=now
        return self.send_pending(now)

    def snapshot(self):
        return dict(pending=self.outbox.count(),dropped=self.outbox.dropped(),acknowledged=self.sent,
                    failed_attempts=self.failures,rejected=self.rejected,last_result=self.last_result,
                    running=bool(self.thread and self.thread.is_alive()),link_paused=self.offline,sampling_paused=self.pause_sampling)

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear()
        def run():
            while not self.stop_event.is_set():
                try:self.step()
                except Exception as exc:self.last_result='Local test-device error: '+type(exc).__name__
                self.stop_event.wait(.2)
        self.thread=threading.Thread(target=run,daemon=True,name='synthetic-test-device');self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=3)
