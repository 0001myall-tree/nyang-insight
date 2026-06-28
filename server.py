#!/usr/bin/env python3
"""
Nyang Insight - 나만의 지식 노트 서버
실행: python3 server.py
접속: http://localhost:8000
"""

import json
import base64
import io
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse
from http.server import HTTPServer, SimpleHTTPRequestHandler

NOTES_FILE = os.path.join(os.path.dirname(__file__), 'notes.json')
BUNDLED_SITE_PACKAGES = (
    '/Users/isoyeon/.cache/codex-runtimes/codex-primary-runtime/'
    'dependencies/python/lib/python3.12/site-packages'
)
if os.path.isdir(BUNDLED_SITE_PACKAGES) and BUNDLED_SITE_PACKAGES not in sys.path:
    sys.path.append(BUNDLED_SITE_PACKAGES)


def load_notes():
    if not os.path.exists(NOTES_FILE):
        return []
    with open(NOTES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_notes(notes):
    with open(NOTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


# ─── youtube-transcript-api 체크 ───
def check_transcript_api():
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        return True
    except ImportError:
        return False


def extract_video_id(url):
    """유튜브 URL에서 video ID 추출"""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def fetch_youtube_transcript(video_id):
    """
    자막 우선순위:
    1. 한국어 수동 자막
    2. 한국어 자동생성 자막
    3. 영어 수동 자막
    4. 영어 자동생성 자막
    5. 사용 가능한 첫 번째 자막
    """
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    # 사용 가능한 자막 목록 수집
    available = []
    for t in transcript_list:
        available.append({
            'lang': t.language_code,
            'generated': t.is_generated,
            'obj': t
        })

    def find(lang, generated=None):
        for a in available:
            if a['lang'] == lang:
                if generated is None or a['generated'] == generated:
                    return a['obj']
        return None

    # 우선순위대로 시도
    chosen = (
        find('ko', False) or
        find('ko', True) or
        find('en', False) or
        find('en', True) or
        (available[0]['obj'] if available else None)
    )

    if not chosen:
        raise Exception('사용 가능한 자막이 없어요.')

    fetched = chosen.fetch()
    lang_used = chosen.language_code
    is_auto = chosen.is_generated

    # 텍스트 합치기 (타임스탬프 제거)
    texts = []
    for snippet in fetched:
        # snippet은 FetchedTranscriptSnippet 객체
        text = snippet.text.strip()
        # 뮤직 태그, 박수 등 제거
        text = re.sub(r'\[.*?\]', '', text).strip()
        if text:
            texts.append(text)

    full_text = ' '.join(texts)
    return {
        'text': full_text,
        'lang': lang_used,
        'is_auto': is_auto,
        'char_count': len(full_text),
        'available_langs': [a['lang'] for a in available]
    }


class ReadableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ''
        self.texts = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg', 'canvas', 'iframe'):
            self.skip_depth += 1
        elif tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg', 'canvas', 'iframe') and self.skip_depth:
            self.skip_depth -= 1
        elif tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        text = re.sub(r'\s+', ' ', data).strip()
        if not text:
            return
        if self.in_title:
            self.title = (self.title + ' ' + text).strip()
        elif not self.skip_depth and len(text) > 1:
            self.texts.append(text)


def fetch_website_content(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise Exception('http 또는 https로 시작하는 웹사이트 URL을 입력해주세요.')

    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X) NyangInsight/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
    )
    with urllib.request.urlopen(req, timeout=12) as res:
        content_type = res.headers.get('Content-Type', '')
        if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
            raise Exception('HTML 웹페이지가 아니어서 본문을 읽기 어려워요.')
        raw = res.read(2_000_000)

    encoding_match = re.search(r'charset=([\w-]+)', content_type, re.I)
    encoding = encoding_match.group(1) if encoding_match else 'utf-8'
    html = raw.decode(encoding, errors='replace')

    parser = ReadableHTMLParser()
    parser.feed(html)
    text = '\n'.join(parser.texts)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    text = re.sub(r'[ \t]{2,}', ' ', text)
    if len(text) < 200:
        raise Exception('본문을 충분히 추출하지 못했어요. 로그인/차단/동적 페이지일 수 있어요.')

    return {
        'title': parser.title[:120] if parser.title else parsed.netloc,
        'text': text[:30000],
        'char_count': len(text),
        'url': url,
    }


def extract_pdf_text(pdf_bytes):
    try:
        import pdfplumber
    except Exception:
        pdfplumber = None

    texts = []
    if pdfplumber:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ''
                if page_text.strip():
                    texts.append(page_text.strip())

    if not texts:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                page_text = page.extract_text() or ''
                if page_text.strip():
                    texts.append(page_text.strip())
        except ImportError:
            raise Exception('PDF 텍스트 추출 도구를 찾지 못했어요.')

    text = '\n\n'.join(texts)
    text = re.sub(r'[ \t]{2,}', ' ', text).strip()
    if len(text) < 100:
        raise Exception('PDF에서 읽을 수 있는 텍스트를 충분히 추출하지 못했어요. 스캔 이미지 PDF일 수 있어요.')
    return text


def fetch_pdf_content(data):
    filename = data.get('filename', 'PDF 문서')
    if data.get('data_base64'):
        pdf_bytes = base64.b64decode(data['data_base64'])
    else:
        source = data.get('url', '').strip()
        if not source:
            raise Exception('PDF 파일을 선택하거나 PDF URL/경로를 입력해주세요.')
        if re.match(r'^https?://', source, re.I):
            req = urllib.request.Request(source, headers={'User-Agent': 'Mozilla/5.0 NyangInsight/1.0'})
            with urllib.request.urlopen(req, timeout=20) as res:
                pdf_bytes = res.read(15_000_000)
            filename = os.path.basename(urlparse(source).path) or filename
        else:
            path = os.path.expanduser(source)
            if not os.path.exists(path):
                raise Exception('PDF 파일 경로를 찾을 수 없어요.')
            filename = os.path.basename(path)
            with open(path, 'rb') as f:
                pdf_bytes = f.read(15_000_000)

    text = extract_pdf_text(pdf_bytes)
    return {
        'title': os.path.splitext(filename)[0] or 'PDF 문서',
        'text': text[:30000],
        'char_count': len(text),
        'filename': filename,
    }


class Handler(SimpleHTTPRequestHandler):

    def log_message(self, format, *args):
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
        elif self.path == '/api/transcript-available':
            self._json({'available': check_transcript_api()})
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/notes':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            notes = json.loads(body.decode('utf-8'))
            save_notes(notes)
            self._json({'ok': True, 'count': len(notes)})

        elif self.path == '/api/youtube-transcript':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))
            url = data.get('url', '').strip()

            if not url:
                return self._error(400, '유튜브 URL을 입력해주세요.')

            if not check_transcript_api():
                return self._error(500,
                    'youtube-transcript-api가 설치되지 않았어요.\n'
                    '터미널에서 아래 명령어를 실행해주세요:\n'
                    'pip install youtube-transcript-api'
                )

            video_id = extract_video_id(url)
            if not video_id:
                return self._error(400, '올바른 유튜브 URL이 아니에요. (예: https://youtube.com/watch?v=xxxx)')

            try:
                result = fetch_youtube_transcript(video_id)
                self._json({
                    'ok': True,
                    'video_id': video_id,
                    **result
                })
            except Exception as e:
                err_msg = str(e)
                # 친화적 에러 메시지
                if 'No transcript' in err_msg or 'Could not retrieve' in err_msg:
                    err_msg = '이 영상에는 자막이 없거나 비공개 영상이에요.'
                elif '403' in err_msg or 'Forbidden' in err_msg:
                    err_msg = '유튜브 접근이 일시적으로 차단됐어요. 잠시 후 다시 시도해주세요.'
                elif 'VideoUnavailable' in err_msg:
                    err_msg = '영상을 찾을 수 없어요. URL을 다시 확인해주세요.'
                self._error(500, err_msg)
        elif self.path == '/api/website-content':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))
            url = data.get('url', '').strip()

            if not url:
                return self._error(400, '웹사이트 URL을 입력해주세요.')
            if not re.match(r'^https?://', url, re.I):
                url = 'https://' + url

            try:
                result = fetch_website_content(url)
                self._json({'ok': True, **result})
            except Exception as e:
                err_msg = str(e)
                if 'timed out' in err_msg.lower():
                    err_msg = '웹사이트 응답이 너무 오래 걸려요. 잠시 후 다시 시도해주세요.'
                elif 'HTTP Error 403' in err_msg:
                    err_msg = '웹사이트에서 자동 접근을 차단했어요.'
                elif 'HTTP Error 404' in err_msg:
                    err_msg = '페이지를 찾을 수 없어요. URL을 확인해주세요.'
                self._error(500, err_msg)
        elif self.path == '/api/pdf-content':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))

            try:
                result = fetch_pdf_content(data)
                self._json({'ok': True, **result})
            except Exception as e:
                err_msg = str(e)
                if 'timed out' in err_msg.lower():
                    err_msg = 'PDF를 가져오는 데 시간이 너무 오래 걸려요.'
                self._error(500, err_msg)
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

    def _error(self, code, message):
        body = json.dumps({'ok': False, 'error': message}, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
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
    # 시작 시 youtube-transcript-api 설치 안내
    if not check_transcript_api():
        print('━' * 40)
        print('  ⚠️  youtube-transcript-api 미설치')
        print('  유튜브 자막 기능을 쓰려면 아래 명령어를 실행하세요:')
        print('  pip install youtube-transcript-api')
        print('━' * 40)
    
    port = 8000
    server = HTTPServer(('localhost', port), Handler)
    print('━' * 40)
    print('  ✨ Nyang Insight 서버 시작!')
    print(f'  👉 브라우저에서 열기: http://localhost:{port}')
    print('  🛑 종료하려면 Ctrl+C')
    print('━' * 40)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  서버를 종료했어요. 또 써요! 👋')
