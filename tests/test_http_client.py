"""Unit test of transport protocol only; never a replacement for the real stack."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from common import Trino

class ProtocolTests(unittest.TestCase):
    def test_pages_are_fully_consumed(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, payload):
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps(payload).encode())
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.reply({'id': 'unit', 'nextUri': f'http://127.0.0.1:{self.server.server_port}/next', 'data': [[1]]})
            def do_GET(self):
                self.reply({'id': 'unit', 'data': [[2]], 'stats': {'processedBytes': 8}})
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        old = os.environ.get('TRINO_URL')
        os.environ['TRINO_URL'] = f'http://127.0.0.1:{server.server_port}'
        try:
            t = Trino()
            self.assertEqual(t.query('SELECT 1'), [[1], [2]])
            self.assertEqual(t.last['stats']['processedBytes'], 8)
        finally:
            server.shutdown(); server.server_close(); thread.join()
            if old is None: del os.environ['TRINO_URL']
            else: os.environ['TRINO_URL'] = old

if __name__ == '__main__': unittest.main()
