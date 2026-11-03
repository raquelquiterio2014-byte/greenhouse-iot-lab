"""V3 local HTTP ingestion. Dedicated test routes cannot populate real history."""
from dataclasses import replace
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from .core import Reading
from .sensors import DEMO_CALIBRATION
from .connectivity import validate_transport,summarize


class Receiver:
    def __init__(self,store,token,host='127.0.0.1',port=8765,device='greenhouse-01',calibration_registry=None):
        if not isinstance(token,str) or len(token)<16:raise ValueError('Token must contain at least 16 characters')
        self.store,self.token,self.host,self.port,self.device=store,token,host,port,device
        self.calibration_registry=calibration_registry
        self.server=None;self.thread=None

    def start(self):
        if self.server:raise RuntimeError('Receiver already running')
        parent=self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup();self.connection.settimeout(3)

            def log_message(self,*args):pass

            def reply(self,code,body):
                data=json.dumps(body,allow_nan=False).encode()
                try:
                    self.send_response(code);self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError,TimeoutError):pass

            def authenticated(self,source):
                ok=hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+parent.token).encode())
                if not ok:
                    parent.store.transport_event(source,'unauthorized',401)
                    self.reply(401,{'error':'Invalid bearer token'})
                return ok

            def body(self):
                if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                    return 415,{'error':'Use application/json'}
                if self.headers.get('Transfer-Encoding'):return 400,{'error':'Chunked requests are not supported'}
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=4096:return 413,{'error':'Body must contain 1-4096 bytes'}
                    data=self.rfile.read(length)
                    if len(data)!=length:raise ValueError('Incomplete body')
                    obj=json.loads(data)
                    if not isinstance(obj,dict):raise ValueError('JSON must be an object')
                    return 200,obj
                except (ValueError,UnicodeDecodeError,TimeoutError) as exc:return 400,{'error':str(exc)}

            def do_GET(self):
                parsed=urlsplit(self.path)
                if parsed.path=='/health':
                    self.reply(200,dict(status='ok',device_id=parent.device,version='4.0.0',physical_actuation=False))
                elif parsed.path=='/api/status':
                    source=parse_qs(parsed.query).get('source',['real'])[0]
                    if source not in ('real','test'):
                        self.reply(400,{'error':'source must be real or test'});return
                    if not self.authenticated(source):return
                    self.reply(200,summarize(parent.store,source))
                else:self.reply(404,{'error':'Not found'})

            def do_POST(self):
                routes={'/api/readings':('real',False),'/api/test/readings':('test',False),
                        '/api/heartbeat':('real',True),'/api/test/heartbeat':('test',True)}
                if self.path not in routes:self.reply(404,{'error':'Not found'});return
                source,heartbeat=routes[self.path]
                if not self.authenticated(source):return
                code,payload=self.body()
                if code!=200:
                    parent.store.transport_event(source,'rejected',code);self.reply(code,payload);return
                try:
                    metadata=validate_transport(payload.pop('transport',None))
                    if heartbeat:
                        if set(payload)-{'device_id','status'} or payload.get('device_id')!=parent.device:
                            raise ValueError('Invalid heartbeat device or fields')
                        status=payload.get('status')
                        if status not in ('ok','sensor_fault'):raise ValueError('Invalid heartbeat status')
                        outcome='sensor_fault' if status=='sensor_fault' else 'heartbeat'
                        parent.store.transport_event(source,outcome,200,metadata=metadata)
                        self.reply(200,dict(accepted=True,source=source,device_status=status));return
                    cal=DEMO_CALIBRATION if source=='test' else (parent.calibration_registry.current if parent.calibration_registry else None)
                    reading=Reading.from_payload(payload,source=source,device=parent.device,calibration=cal)
                    reading=replace(reading,transport_snapshot=json.dumps(metadata,sort_keys=True))
                except ValueError as exc:
                    parent.store.transport_event(source,'rejected',400)
                    self.reply(400,{'error':str(exc)});return
                try:
                    outcome=parent.store.ingest(reading)
                    code=201 if outcome=='accepted' else (409 if outcome=='conflict' else 200)
                    parent.store.transport_event(source,outcome,code,reading.sample_id,metadata)
                    self.reply(code,dict(accepted=outcome!='conflict',duplicate=outcome=='duplicate',source=source,
                        sample_id=reading.sample_id,error='Sample ID reused with different measurements' if outcome=='conflict' else None))
                except Exception:
                    self.reply(503,{'error':'Local storage unavailable; retry this sample_id'})

        class Server(ThreadingHTTPServer):
            daemon_threads=True
            allow_reuse_address=True

        self.server=Server((self.host,self.port),Handler)
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.1),daemon=True,name='iot-http')
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.server=None
