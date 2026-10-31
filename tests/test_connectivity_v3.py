import json
import tempfile
import time
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from greenhouse.core import Store,Reading
from greenhouse.sensors import CalibrationRegistry,DEMO_CALIBRATION
from greenhouse.receiver import Receiver
from greenhouse.connectivity import summarize,validate_transport
from greenhouse.device_client import DeviceClient,Outbox,post_json


def payload(sid='boot:1',**updates):
    data=dict(device_id='greenhouse-01',sample_id=sid,schema_version=2,
        temperature=24.8,humidity=62,soil_raw=2316,soil_mv=1800,light_raw=864,adc_samples=10,
        transport=dict(boot_id='boot',sequence=1,queue_depth=1,dropped_samples=0,uptime_ms=100,firmware_version='3.0.0'))
    data.update(updates);return data


class TransportIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=Store(self.root/'observations.sqlite3');self.token='test-only-token-at-least16'
        self.registry=CalibrationRegistry(self.root/'calibration.json')
        self.receiver=Receiver(self.store,self.token,port=0,calibration_registry=self.registry)
        self.receiver.start();self.addCleanup(self.receiver.stop)
        self.url=f'http://127.0.0.1:{self.receiver.port}'

    def post(self,path,data,token=None):return post_json(self.url+path,token or self.token,data)

    def get(self,path,token=None):
        req=Request(self.url+path,headers={'Authorization':'Bearer '+(token or self.token)})
        try:
            with urlopen(req,timeout=2) as r:return r.status,json.loads(r.read())
        except HTTPError as e:return e.code,json.loads(e.read())

    def client(self,sender=post_json):
        return DeviceClient(self.url+'/api/test/readings',self.token,Outbox(self.root/'outbox.sqlite3'),sender=sender)

    def test_sources_are_separate(self):
        code,body=self.post('/api/test/readings',payload())
        self.assertEqual(code,201);self.assertEqual(body['source'],'test')
        self.assertEqual(self.store.count('test'),1);self.assertEqual(self.store.count('real'),0)
        self.assertEqual(self.store.count('demo'),0)
        self.assertEqual(self.store.recent('test')[-1]['quality'],'OK')
        self.post('/api/readings',payload())
        self.assertEqual(self.store.count('real'),1)
        self.assertIn('CALIBRATION_REQUIRED',self.store.recent('real')[-1]['quality'])

    def test_client_refuses_physical_route_and_nonloopback(self):
        for url in [self.url+'/api/readings','http://192.168.1.2:8765/api/test/readings',
                    self.url+'/api/test/readings?x=1','https://127.0.0.1/api/test/readings']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                DeviceClient(url,self.token,Outbox(self.root/'queue.sqlite3'))

    def test_lost_ack_retries_without_duplicate_storage(self):
        calls=[]
        def lose_ack(url,token,data):
            response=post_json(url,token,data);calls.append(response[0])
            return (0,{}) if len(calls)==1 else response
        client=self.client(lose_ack);now=time.time();client.outbox.enqueue(payload(),now)
        self.assertEqual(client.send_pending(now),'retry');self.assertEqual(client.outbox.count(),1)
        self.assertEqual(client.send_pending(now+2),'acknowledged');self.assertEqual(client.outbox.count(),0)
        self.assertEqual(calls,[201,200]);self.assertEqual(self.store.count('test'),1)
        state=summarize(self.store,'test');self.assertEqual(state['counts']['duplicate'],1)
        self.assertEqual(self.store.count('real'),0)

    def test_conflicting_id_does_not_overwrite(self):
        self.post('/api/test/readings',payload())
        code,body=self.post('/api/test/readings',payload(temperature=30))
        self.assertEqual(code,409);self.assertFalse(body['accepted'])
        self.assertEqual(self.store.recent('test')[-1]['temperature'],24.8)
        self.assertEqual(summarize(self.store,'test')['counts']['conflict'],1)

    def test_unauthorized_not_contact_or_measurement(self):
        self.assertEqual(self.post('/api/readings',payload(),token='wrong')[0],401)
        state=summarize(self.store,'real');self.assertEqual(state['contact_state'],'WAITING')
        self.assertEqual(state['measurement_state'],'NO_DATA');self.assertEqual(state['stored_samples'],0)
        self.assertEqual(state['counts']['unauthorized'],1)

    def test_sensor_fault_heartbeat_does_not_create_reading(self):
        code,_=self.post('/api/heartbeat',dict(device_id='greenhouse-01',status='sensor_fault',transport={}))
        self.assertEqual(code,200)
        state=summarize(self.store,'real');self.assertEqual(state['contact_state'],'ACTIVE')
        self.assertEqual(state['measurement_state'],'NO_DATA');self.assertEqual(state['sensor_status'],'FAULT')
        self.assertEqual(self.store.count('real'),0)

    def test_backfill_contact_is_fresh_but_measurement_is_stale(self):
        self.post('/api/test/readings',payload(sample_age_seconds=600))
        self.post('/api/test/heartbeat',dict(device_id='greenhouse-01',status='ok'))
        state=summarize(self.store,'test')
        self.assertEqual(state['contact_state'],'ACTIVE');self.assertEqual(state['measurement_state'],'STALE')
        self.assertGreaterEqual(state['measurement_age_seconds'],600)

    def test_sensor_fault_not_hidden_by_old_queued_measurement(self):
        self.post('/api/heartbeat',dict(device_id='greenhouse-01',status='sensor_fault'))
        self.post('/api/readings',payload(sample_age_seconds=600))
        self.assertEqual(summarize(self.store,'real')['sensor_status'],'FAULT')

    def test_status_endpoint_is_authenticated_and_has_no_secret(self):
        self.assertEqual(self.get('/api/status?source=test',token='bad')[0],401)
        code,body=self.get('/api/status?source=test');self.assertEqual(code,200)
        self.assertNotIn(self.token,json.dumps(body));self.assertEqual(body['hardware_validation'],'PENDING')
        self.assertEqual(self.get('/api/status?source=demo')[0],400)

    def test_reject_invalid_metadata_without_saving(self):
        for fields in [dict(queue_depth=33),dict(sequence=True),dict(boot_id='a b'),dict(password='no')]:
            with self.subTest(fields=fields):self.assertEqual(self.post('/api/test/readings',payload(transport=fields))[0],400)
        self.assertEqual(self.store.count('test'),0)

    def test_provenance_in_history_and_csv(self):
        self.post('/api/test/readings',payload())
        row=self.store.recent('test')[-1]
        self.assertEqual(json.loads(row['transport_snapshot'])['firmware_version'],'3.0.0')
        self.store.export('test',self.root/'out.csv')
        self.assertIn('transport_snapshot',(self.root/'out.csv').read_text(encoding='utf-8-sig'))

    def test_receiver_restart_acknowledges_existing_sample(self):
        self.post('/api/test/readings',payload());port=self.receiver.port
        self.receiver.stop();self.receiver.start();self.assertEqual(self.receiver.port,port)
        self.assertEqual(self.post('/api/test/readings',payload())[0],200)
        self.assertEqual(self.store.count('test'),1)

    def test_client_survives_stopped_receiver_and_later_drains(self):
        client=self.client();now=time.time();client.outbox.enqueue(payload(),now)
        self.receiver.stop();self.assertEqual(client.send_pending(now),'retry')
        self.assertEqual(client.outbox.count(),1)
        self.receiver.start();self.assertEqual(client.send_pending(now+2),'acknowledged')
        self.assertEqual(client.outbox.count(),0);self.assertEqual(self.store.count('real'),0)

    def test_contact_expires_independently(self):
        self.post('/api/test/readings',payload())
        later=datetime.now(timezone.utc)+timedelta(seconds=100)
        state=summarize(self.store,'test',now=later)
        self.assertEqual(state['contact_state'],'SILENT');self.assertEqual(state['measurement_state'],'FRESH')


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'outbox.sqlite3'

    def test_queue_capacity_and_persistence(self):
        box=Outbox(self.path)
        for i in range(35):box.enqueue(payload(str(i)),now=100+i)
        self.assertEqual(box.count(),32);self.assertEqual(box.dropped(),3)
        self.assertEqual(box.head()['sample_id'],'3')
        restored=Outbox(self.path);self.assertEqual(restored.count(),32);self.assertEqual(restored.dropped(),3)

    def test_repeated_enqueue_does_not_evict(self):
        box=Outbox(self.path,capacity=1);box.enqueue(payload());box.enqueue(payload())
        self.assertEqual(box.count(),1);self.assertEqual(box.dropped(),0)

    def test_auth_failure_retains_queue_and_backs_off(self):
        box=Outbox(self.path);box.enqueue(payload(),now=100)
        client=DeviceClient('http://127.0.0.1:8765/api/test/readings','x',box,sender=lambda *a:(401,{}))
        self.assertEqual(client.send_pending(100),'retry');self.assertEqual(box.count(),1)
        self.assertEqual(box.head()['next_retry'],130)
        self.assertEqual(client.send_pending(101),'backoff')

    def test_bad_ack_is_not_delivery(self):
        for body in [dict(accepted=True,sample_id='wrong',source='test'),
                     dict(accepted=True,sample_id='boot:1',source='real'),[]]:
            with self.subTest(body=body):
                box=Outbox(self.path);box.enqueue(payload(),now=100)
                client=DeviceClient('http://127.0.0.1:8765/api/test/readings','x',box,sender=lambda *a:(200,body))
                self.assertEqual(client.send_pending(100),'retry');self.assertEqual(box.count(),1)
                box.acknowledge(box.head())

    def test_permanent_rejection_moves_to_rejected(self):
        box=Outbox(self.path);box.enqueue(payload(),now=100)
        client=DeviceClient('http://127.0.0.1:8765/api/test/readings','x',box,sender=lambda *a:(409,{}))
        self.assertEqual(client.send_pending(100),'rejected');self.assertEqual(box.count(),0)
        with box.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM rejected').fetchone()[0],1)

    def test_offline_keeps_pending(self):
        box=Outbox(self.path);box.enqueue(payload(),now=100)
        client=DeviceClient('http://127.0.0.1:8765/api/test/readings','x',box);client.offline=True
        self.assertEqual(client.send_pending(100),'offline');self.assertEqual(box.count(),1)

    def test_expired_is_removed_without_send(self):
        box=Outbox(self.path);box.enqueue(payload(),now=100)
        def must_not_send(*args):raise AssertionError('Expired sample was sent')
        client=DeviceClient('http://127.0.0.1:8765/api/test/readings','x',box,sender=must_not_send)
        self.assertEqual(client.send_pending(100+86401),'expired');self.assertEqual(box.count(),0)


if __name__=='__main__':unittest.main()
