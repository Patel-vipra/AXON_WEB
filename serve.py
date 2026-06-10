#!/usr/bin/env python3
"""
AXON Showcase — Local Network Live-Reload Server
No external dependencies. Run: python3 serve.py
"""
import http.server
import socketserver
import os
import socket
import threading
import queue
import time

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8080
WATCH_FILE = os.path.join(DEMO_DIR, 'axon-showcase.html')

LIVE_RELOAD_SCRIPT = b"""
<script>
(function(){
  var es = new EventSource('/events');
  es.onmessage = function(e){ if(e.data==='reload') location.reload(); };
  es.onerror   = function(){ setTimeout(function(){ location.reload(); }, 1500); };
})();
</script>
"""

_clients = []
_clients_lock = threading.Lock()
_last_mtime = [None]


def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def _watch_loop():
    try:
        _last_mtime[0] = os.path.getmtime(WATCH_FILE)
    except OSError:
        pass
    while True:
        time.sleep(0.4)
        try:
            mtime = os.path.getmtime(WATCH_FILE)
            if _last_mtime[0] is not None and mtime != _last_mtime[0]:
                _last_mtime[0] = mtime
                with _clients_lock:
                    for q in list(_clients):
                        try:
                            q.put_nowait('reload')
                        except queue.Full:
                            pass
            else:
                _last_mtime[0] = mtime
        except OSError:
            pass


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DEMO_DIR, **kwargs)

    def do_GET(self):
        # Root redirect
        if self.path in ('/', ''):
            self.send_response(302)
            self.send_header('Location', '/axon-showcase.html')
            self.end_headers()
            return

        # SSE live-reload endpoint
        if self.path == '/events':
            self._handle_events()
            return

        # HTML files — inject live-reload script
        local_path = self.translate_path(self.path)
        if local_path.endswith('.html') and os.path.isfile(local_path):
            try:
                with open(local_path, 'rb') as f:
                    content = f.read()
                injected = content.replace(b'</body>', LIVE_RELOAD_SCRIPT + b'</body>', 1)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(injected)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(injected)
            except Exception as exc:
                self.send_error(500, str(exc))
            return

        # Everything else (PNG, MP4, etc.)
        super().do_GET()

    def _handle_events(self):
        q = queue.Queue(maxsize=10)
        with _clients_lock:
            _clients.append(q)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    self.wfile.write(f'data: {msg}\n\n'.encode())
                    self.wfile.flush()
                except queue.Empty:
                    # keepalive ping
                    self.wfile.write(b': ping\n\n')
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            with _clients_lock:
                try:
                    _clients.remove(q)
                except ValueError:
                    pass

    def log_message(self, fmt, *args):
        # Only log non-asset requests to keep the terminal clean
        path = args[0] if args else ''
        if not any(path.endswith(ext) for ext in ('.png', '.mp4', '.ico', '/events')):
            print(f'  [{self.address_string()}] {fmt % args}')


def main():
    ip = _get_local_ip()
    threading.Thread(target=_watch_loop, daemon=True).start()

    print()
    print('  ╔═══════════════════════════════════════════╗')
    print('  ║        AXON Showcase — Live Server        ║')
    print('  ╚═══════════════════════════════════════════╝')
    print()
    print(f'  Local:   http://localhost:{PORT}/axon-showcase.html')
    print(f'  Network: http://{ip}:{PORT}/axon-showcase.html')
    print()
    print('  → Open the Network URL on your phone (same WiFi)')
    print('  → Edit axon-showcase.html and save → page reloads on ALL devices')
    print()
    print('  Press Ctrl+C to stop')
    print()

    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        httpd.socket.setsockopt(
            socketserver.socket.SOL_SOCKET,
            socketserver.socket.SO_REUSEADDR, 1
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n  Server stopped.\n')


if __name__ == '__main__':
    main()
