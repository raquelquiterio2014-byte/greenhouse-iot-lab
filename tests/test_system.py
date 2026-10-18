import csv
import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from greenhouse.core import Reading, Store, Simulator, Irrigation, alerts
from greenhouse.receiver import Receiver


def payload(sample='sample-1', **updates):
    p = dict(device_id='greenhouse-01', sample_id=sample, temperature=24.8,
             humidity=62, soil_moisture=38, light_lux=720, sample_age_seconds=0)
    p.update(updates); return p


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/'test.sqlite3')

    def test_ranges_and_non_finite(self):
        for key,value in [('temperature',81),('humidity',-1),('soil_moisture',101),
                          ('light_lux',-1),('temperature',float('nan')),
                          ('humidity',float('inf')),('humidity',True),('humidity','62')]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                Reading.from_payload(payload(**{key:value}))

    def test_missing_and_unknown_fields(self):
        p=payload();del p['humidity']
        with self.assertRaises(ValueError):Reading.from_payload(p)
        with self.assertRaises(ValueError):Reading.from_payload(payload(source='demo'))
        with self.assertRaises(ValueError):Reading.from_payload(payload(device_id='other'))
        with self.assertRaises(ValueError):Reading.from_payload(payload(sample_id=''))

    def test_age_and_stale_data(self):
        r=Reading.from_payload(payload(sample_age_seconds=300))
        self.assertGreaterEqual(r.age(),300)
        self.assertIn('STALE',alerts(r)[0])
        with self.assertRaises(ValueError):Reading.from_payload(payload(sample_age_seconds=-1))

    def test_idempotency_and_source_isolation(self):
        r=Reading.from_payload(payload())
        self.assertTrue(self.store.add(r));self.assertFalse(self.store.add(r))
        self.store.add(Reading.from_payload(payload(),source='demo'))
        self.assertEqual(self.store.count('real'),1);self.assertEqual(self.store.count('demo'),1)

    def test_backfill_does_not_replace_latest_measurement(self):
        self.store.add(Reading.from_payload(payload('fresh')))
        self.store.add(Reading.from_payload(payload('offline',sample_age_seconds=600)))
        self.assertEqual(self.store.recent('real',1)[-1]['sample_id'],'fresh')

    def test_export_all_samples_not_only_chart_window(self):
        for i in range(130):self.store.add(Reading.from_payload(payload(str(i))))
        path=Path(self.temp.name)/'export.csv';self.store.export('real',path)
        with path.open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),130)
        self.assertEqual(rows[0]['source'],'real')

    def test_thread_safe_storage(self):
        def add(i):self.store.add(Reading.from_payload(payload(str(i))))
        with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(add,range(30)))
        self.assertEqual(self.store.count('real'),30)

    def test_expected_initial_values(self):
        r=Simulator(7).sample(advance=False)
        self.assertEqual((r.temperature,r.humidity,r.soil_moisture,r.light_lux),(24.8,62,38,720))
        self.assertEqual(r.source,'demo')

    def test_demo_scenarios(self):
        s=Simulator(3);s.set_scenario('Dry soil')
        r=s.sample(advance=False);self.assertLess(r.soil_moisture,35)
        self.assertIn('Dry soil',alerts(r)[0])
        s.set_scenario('Hot day');self.assertIn('High air',alerts(s.sample(False,False))[0])
        s.set_scenario('Night');self.assertLess(s.sample(False,False).light_lux,10)


class RuleTests(unittest.TestCase):
    def test_dry_starts_and_recovery_stops(self):
        i=Irrigation();self.assertIsNotNone(i.update(25,now=0));self.assertTrue(i.active)
        i.update(45,now=2);self.assertFalse(i.active)

    def test_hysteresis(self):
        i=Irrigation();i.update(34,now=0);i.update(38,now=1);self.assertTrue(i.active)

    def test_timeout_locks_until_recovery(self):
        i=Irrigation();i.update(25,now=0);i.update(25,now=21)
        self.assertFalse(i.active);self.assertTrue(i.locked)
        i.update(25,now=22);self.assertFalse(i.active)
        i.update(45,now=23);self.assertFalse(i.locked)
        i.update(25,now=24);self.assertTrue(i.active)

    def test_stale_disables_simulated_actuator(self):
        i=Irrigation();i.update(25,now=0);i.update(25,fresh=False,now=1)
        self.assertFalse(i.active)

    def test_manual_timer_and_automatic_disabled(self):
        i=Irrigation();i.automatic=False;i.start(now=0,duration=10)
        i.update(38,now=11);self.assertFalse(i.active)
        i.update(20,now=12);self.assertFalse(i.active)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'http.sqlite3')
        self.token='test-token-at-least-16-chars'
        self.receiver=Receiver(self.store,self.token,port=0);self.receiver.start()
        self.addCleanup(self.receiver.stop)
        self.url=f'http://127.0.0.1:{self.receiver.port}'

    def post(self,p,token=None,content_type='application/json'):
        req=Request(self.url+'/api/readings',data=json.dumps(p).encode(),headers={
            'Content-Type':content_type,'Authorization':'Bearer '+(self.token if token is None else token)})
        try:
            with urlopen(req,timeout=4) as r:return r.status,json.loads(r.read())
        except HTTPError as e:return e.code,json.loads(e.read())

    def test_real_roundtrip_and_duplicate(self):
        self.assertEqual(self.post(payload())[0],201)
        status,body=self.post(payload());self.assertEqual(status,200);self.assertTrue(body['duplicate'])
        self.assertEqual(self.store.count('real'),1);self.assertEqual(self.store.count('demo'),0)

    def test_unauthorized_and_invalid_data_are_not_saved(self):
        self.assertEqual(self.post(payload(),token='wrong')[0],401)
        self.assertEqual(self.post(payload(humidity=110))[0],400)
        self.assertEqual(self.post(payload(temperature=float('nan')))[0],400)
        self.assertEqual(self.post(payload(),content_type='text/plain')[0],415)
        self.assertEqual(self.store.count('real'),0)

    def test_health(self):
        with urlopen(self.url+'/health',timeout=4) as r:
            self.assertEqual(json.loads(r.read())['status'],'ok')

    def test_oversized_body(self):
        status,_=self.post({'padding':'x'*5000});self.assertEqual(status,413)

    def test_offline_backfill_keeps_original_age(self):
        self.assertEqual(self.post(payload(sample_age_seconds=500))[0],201)
        row=self.store.recent('real')[-1]
        self.assertIn('STALE',alerts(Reading(**{k:row[k] for k in Reading.__dataclass_fields__}))[0])


if __name__=='__main__':unittest.main()
