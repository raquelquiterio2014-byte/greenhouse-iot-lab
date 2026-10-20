"""Small authenticated local receiver; no Tk calls on background threads."""
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .core import Reading


class Receiver:
    def __init__(self, store, token, host='127.0.0.1', port=8765, device='greenhouse-01', calibration_registry=None):
        if not isinstance(token, str) or len(token) < 16:
            raise ValueError('Token must contain at least 16 characters')
        self.calibration_registry = calibration_registry
        self.store, self.token, self.host, self.port, self.device = store, token, host, port, device
        self.server = None
        self.thread = None

    def start(self):
        parent = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == '/health':
                    self.reply(200, {'status': 'ok', 'device_id': parent.device})
                else:
                    self.reply(404, {'error': 'Not found'})

            def do_POST(self):
                if self.path != '/api/readings':
                    self.reply(404, {'error': 'Not found'}); return
                auth = self.headers.get('Authorization', '')
                if not hmac.compare_digest(auth.encode(), ('Bearer '+parent.token).encode()):
                    self.reply(401, {'error': 'Invalid bearer token'}); return
                if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                    self.reply(415, {'error': 'Use application/json'}); return
                if self.headers.get('Transfer-Encoding'):
                    self.reply(400, {'error': 'Chunked requests are not supported'}); return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 4096:
                        self.reply(413, {'error': 'Body must contain 1-4096 bytes'}); return
                    self.connection.settimeout(3)
                    data = self.rfile.read(length)
                    if len(data) != length:
                        raise ValueError('Incomplete body')
                    # Python's JSON decoder accepts NaN; Reading rejects all non-finite values.
                    payload = json.loads(data)
                    cal = parent.calibration_registry.current if parent.calibration_registry else None
                    reading = Reading.from_payload(payload, device=parent.device, calibration=cal)
                except (ValueError, UnicodeDecodeError, TimeoutError) as exc:
                    self.reply(400, {'error': str(exc)}); return
                try:
                    inserted = parent.store.add(reading)
                    self.reply(201 if inserted else 200, {'accepted': True, 'duplicate': not inserted})
                except Exception:
                    self.reply(503, {'error': 'Local storage unavailable; retry this sample_id'})

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.server = Server((self.host, self.port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='iot-http')
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = None
