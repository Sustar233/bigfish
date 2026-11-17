"""Transport regression: an idle NapCat SSE connection must stay connected."""
import http.server
import tempfile
import threading
import time
import unittest
from pathlib import Path

import bridge


class IdleSseTest(unittest.TestCase):
    def test_message_after_31_seconds_of_silence_is_received(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.flush()
                time.sleep(31)
                self.wfile.write(b'data: {"test":"after-idle"}\n\n')
                self.wfile.flush()

            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                store = bridge.Store(Path(directory) / 'state.db')
                try:
                    config = {'onebot_url': f'http://127.0.0.1:{server.server_port}',
                              'onebot_token': 'test-only'}
                    client = bridge.Bridge(config, store)
                    with client.request('_events', stream=True) as response:
                        self.assertEqual(response.readline(), b'data: {"test":"after-idle"}\n')
                finally:
                    store.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
