import csv,json,sqlite3,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from urllib.request import Request,urlopen
from greenhouse.core import Reading,Store,Simulator,alerts
from greenhouse.sensors import (Calibration,CalibrationRegistry,DEMO_CALIBRATION,BH1750_MAX_LUX,
                               two_point,mean_adc,ideal_adc_voltage,soil_usable)
from greenhouse.receiver import Receiver


def v2(sid='v2:1',**kw):
    p=dict(schema_version=2,device_id='greenhouse-01',sample_id=sid,temperature=24.8,
           humidity=62,soil_raw=2316,soil_mv=1800,light_raw=864,adc_samples=10)
    p.update(kw);return p


class SensorTests(unittest.TestCase):
    def test_raw_to_index_and_lux(self):
        r=Reading.from_payload(v2(),calibration=DEMO_CALIBRATION)
        self.assertEqual((r.soil_moisture,r.light_lux,r.soil_mv),(38,720,1800))
        self.assertEqual(r.quality,'OK');self.assertTrue(soil_usable(r))

    def test_unconfirmed_is_not_usable_or_dry_alarm(self):
        r=Reading.from_payload(v2(soil_raw=2900))
        self.assertIn('CALIBRATION_REQUIRED',r.quality);self.assertFalse(soil_usable(r))
        self.assertNotIn('Dry soil',' '.join(alerts(r)))

    def test_offsets_keep_raw_and_snapshot(self):
        c=replace(DEMO_CALIBRATION,temperature_offset=-.7,humidity_offset=1)
        r=Reading.from_payload(v2(),calibration=c)
        self.assertEqual((r.temperature,r.temperature_raw,r.humidity,r.humidity_raw),(24.1,24.8,63,62))
        self.assertEqual(json.loads(r.calibration_snapshot)['temperature_offset'],-.7)

    def test_invalid_calibration(self):
        for c in [Calibration(dry_raw=1200),Calibration(wet_raw=float('nan')),Calibration(dry_raw=4095),
                  Calibration(dry_raw=1220),Calibration(confirmed=True),Calibration(temperature_offset=6)]:
            with self.subTest(c=c),self.assertRaises(ValueError):c.validate()

    def test_reversed_polarity(self):
        c=replace(DEMO_CALIBRATION,dry_raw=1200,wet_raw=3000)
        self.assertEqual(Reading.from_payload(v2(soil_raw=2100),calibration=c).soil_moisture,50)

    def test_outside_reference_is_flagged(self):
        r=Reading.from_payload(v2(soil_raw=3500),calibration=DEMO_CALIBRATION)
        self.assertEqual(r.soil_moisture,0);self.assertLess(r.soil_unclamped,0)
        self.assertIn('SOIL_OUTSIDE_CALIBRATION',r.quality);self.assertFalse(soil_usable(r))

    def test_rail_and_saturation(self):
        r=Reading.from_payload(v2(soil_raw=4095,light_raw=65535),calibration=DEMO_CALIBRATION)
        self.assertIn('SOIL_ADC_AT_RAIL',r.quality);self.assertIn('LIGHT_SATURATED',r.quality)
        self.assertEqual(r.light_lux,BH1750_MAX_LUX)

    def test_illegal_payload_fields_and_types(self):
        for update in [dict(light_raw=65536),dict(light_raw=1.5),dict(light_raw=True),dict(soil_raw=-1),
                       dict(soil_mv=3301),dict(adc_samples=1),dict(adc_samples=True),dict(schema_version=True),
                       dict(soil_raw=float('inf')),dict(soil_moisture=38)]:
            with self.subTest(update=update),self.assertRaises(ValueError):Reading.from_payload(v2(**update))

    def test_adc_and_two_point_math(self):
        self.assertAlmostEqual(ideal_adc_voltage(2047.5),1.65)
        with self.assertRaises(ValueError):ideal_adc_voltage(5000)
        self.assertAlmostEqual(mean_adc([2100,2200,2300]),2200)
        with self.assertRaises(ValueError):mean_adc([])
        self.assertAlmostEqual(two_point(30,.8,0,101.2,99.5),28.938247,places=4)

    def test_v1_range_and_legacy_quality(self):
        p=dict(device_id='greenhouse-01',sample_id='old',temperature=20,humidity=60,soil_moisture=40,light_lux=200000)
        with self.assertRaises(ValueError):Reading.from_payload(p)
        p['light_lux']=720;r=Reading.from_payload(p)
        self.assertEqual(r.quality,'LEGACY_NO_RAW');self.assertFalse(soil_usable(r))

    def test_saturation_scenario(self):
        s=Simulator();s.set_scenario('Light saturation')
        self.assertIn('LIGHT_SATURATED',s.sample(advance=False).quality)


class PersistenceV2(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)

    def test_migration_preserves_v1(self):
        path=self.folder/'old.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE readings (id INTEGER PRIMARY KEY,source TEXT,device_id TEXT,sample_id TEXT,measured_at TEXT,received_at TEXT,temperature REAL,humidity REAL,soil_moisture REAL,light_lux REAL,UNIQUE(source,device_id,sample_id))')
            db.execute("INSERT INTO readings VALUES (1,'real','greenhouse-01','old','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00',20,60,40,720)")
        store=Store(path);row=store.recent('real')[0]
        self.assertEqual(row['id'],1);self.assertEqual(row['quality'],'LEGACY_NO_RAW');self.assertIsNone(row['soil_raw'])
        store.add(Reading.from_payload(v2(),calibration=DEMO_CALIBRATION));self.assertEqual(store.count('real'),2)

    def test_revision_persistence_and_immutable_history(self):
        store=Store(self.folder/'history.sqlite3');registry=CalibrationRegistry(self.folder/'cal.json')
        first=registry.save(DEMO_CALIBRATION);store.add(Reading.from_payload(v2(),calibration=first))
        registry.save(replace(first,dry_raw=3200,reference='New measured references'))
        old=store.recent('real')[-1]
        self.assertEqual(old['calibration_id'],first.revision);self.assertEqual(old['soil_moisture'],38)
        self.assertNotEqual(registry.current.revision,first.revision)
        self.assertEqual(CalibrationRegistry(self.folder/'cal.json').current,registry.current)
        path=self.folder/'out.csv';store.export('real',path)
        with path.open(encoding='utf-8-sig') as f:row=list(csv.DictReader(f))[0]
        self.assertEqual(row['calibration_id'],first.revision);self.assertIn('dry_raw',row['calibration_snapshot'])

    def test_http_registry_and_dedup(self):
        registry=CalibrationRegistry(self.folder/'cal.json');registry.save(DEMO_CALIBRATION)
        store=Store(self.folder/'live.sqlite3');token='test-secret-at-least16'
        receiver=Receiver(store,token,port=0,calibration_registry=registry);receiver.start();self.addCleanup(receiver.stop)
        def send():
            req=Request(f'http://127.0.0.1:{receiver.port}/api/readings',data=json.dumps(v2()).encode(),headers={
                'Content-Type':'application/json','Authorization':'Bearer '+token})
            with urlopen(req,timeout=3) as r:return r.status
        self.assertEqual(send(),201);registry.save(replace(registry.current,dry_raw=3200))
        self.assertEqual(send(),200);self.assertEqual(store.count('real'),1)
        row=store.recent('real')[0];self.assertEqual(row['soil_moisture'],38);self.assertEqual(row['schema_version'],2)
