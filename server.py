#!/usr/bin/env python3
"""
Clear Insight - 나만의 지식 노트 서버
실행: python3 server.py
접속: http://localhost:8000
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

NOTES_FILE = os.path.join(os.path.dirname(__file__), 'notes.json')


def load_notes():
    if not os.path.exists(NOTES_FILE):
        return []
    with open(NOTES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_notes(notes):
    with open(NOTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


class Handler(SimpleHTTPRequestHandler):

    def log_message(self, format, *args):
        # 깔끔한 로그
        if '/api/' in args[0]:
            print(f'  [{args[1]}] {args[0].split()[1]}')

    def do_GET(self):
        if self.path == '/api/notes':
            self._json(load_notes())
        elif self.path == '/api/size':
            size = os.path.getsize(NOTES_FILE) if os.path.exists(NOTES_FILE) else 0
            self._json({
                'size_kb': round(size / 1024, 1),
                'size_mb': round(size / 1024 / 1024, 3)
            })
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/notes':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            notes = json.loads(body.decode('utf-8'))
            save_notes(notes)
            self._json({'ok': True, 'count': len(notes)})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')


if __name__ == '__main__':
    port = 8000
    server = HTTPServer(('localhost', port), Handler)
    print('━' * 40)
    print('  ✨ Clear Insight 서버 시작!')
    print(f'  👉 브라우저에서 열기: http://localhost:{port}')
    print('  🛑 종료하려면 Ctrl+C')
    print('━' * 40)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  서버를 종료했어요. 또 써요! 👋')
