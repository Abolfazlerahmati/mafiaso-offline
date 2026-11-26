#!/usr/bin/env python3
"""Minimal local Socket.IO + HTTP server for Pesarkhande (Mafioso) 3.4.2 offline mode.

Usage:
  1. Run on PC:  python server/offline_server.py
     Forward from phone:  adb reverse tcp:8080 tcp:8080
  2. Or run directly on Android (Termux):  python offline_server.py
"""
import http.server
import json
import socketserver
import time
from urllib.parse import urlparse

PORT = 8080

PROFILE = {
    "gold": 9999999,
    "gem": 9999999,
    "trophy": 1000,
    "maxTrophy": 1000,
    "experience": 1000,
    "arena": 1,
    "playerName": "Offline",
    "deck": [1, 2, 3, 4, 5, 6, 7, 8],
    "heros": [{"id": i, "level": 1, "count": 100} for i in range(1, 41)],
}


class OfflineHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        print(f"[GET] {parsed.path}?{parsed.query}")
        # Socket.IO v2/v3 polling handshake
        if parsed.path.startswith("/socket.io"):
            if "sid=" not in parsed.query:
                payload = json.dumps({
                    "sid": "offline-sid-001",
                    "upgrades": [],
                    "pingInterval": 25000,
                    "pingTimeout": 60000,
                })
                body = f"0{payload}".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=UTF-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            # Subsequent polling GET -> return empty/ack or queued events
            body = b"40"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=UTF-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps({"ok": True, "profile": PROFILE}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        print(f"[POST] {self.path} body={raw[:200]}")
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), OfflineHandler) as httpd:
        print(f"Mafioso offline server listening on http://127.0.0.1:{PORT}")
        print("If running on PC, run: adb reverse tcp:8080 tcp:8080")
        httpd.serve_forever()
