#!/usr/bin/env python3
import base64
import hashlib
import hmac
import io
import json
import os
import shlex
import subprocess
import threading
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from PIL import Image

ADB = os.environ.get('ADB', 'adb')
SERIAL = os.environ.get('ANDROID_SERIAL', 'emulator-5554')
SECRET = os.environ['TAKARADA_REMOTE_SECRET']
PORT = int(os.environ.get('TAKARADA_REMOTE_PORT', '8765'))
COOKIE_VALUE = hashlib.sha256((SECRET + '|takarada-remote').encode()).hexdigest()
ASSIST_TOKEN = hashlib.sha256((SECRET + '|assistant-api').encode()).hexdigest()
HOSTSHOT_DIR = '/tmp/takarada-hostshot'
SHOT_LOCK = threading.Lock()
os.makedirs(HOSTSHOT_DIR, exist_ok=True)


def adb(*args, timeout=15):
    return subprocess.run([ADB, '-s', SERIAL, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def screenshot():
    with SHOT_LOCK:
        try:
            for name in os.listdir(HOSTSHOT_DIR):
                if name.lower().endswith('.png'):
                    try:
                        os.remove(os.path.join(HOSTSHOT_DIR, name))
                    except OSError:
                        pass
            p = adb('emu', 'screenrecord', 'screenshot', HOSTSHOT_DIR, timeout=20)
            if p.returncode == 0:
                shots = [os.path.join(HOSTSHOT_DIR, n) for n in os.listdir(HOSTSHOT_DIR) if n.lower().endswith('.png')]
                if shots:
                    newest = max(shots, key=os.path.getmtime)
                    with open(newest, 'rb') as f:
                        data = f.read()
                    if data.startswith(b'\x89PNG') and len(data) > 1000:
                        return data
        except Exception:
            pass
        p = adb('exec-out', 'screencap', '-p', timeout=20)
        return p.stdout if p.returncode == 0 else b''


def screenshot_text():
    data = screenshot()
    if not data:
        return b''
    im = Image.open(io.BytesIO(data)).convert('RGB')
    im.thumbnail((360, 640), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    im.save(out, 'JPEG', quality=48, optimize=True)
    return base64.b64encode(out.getvalue())


def type_text(text):
    text = str(text)
    encoded = text.replace('%', '%%').replace(' ', '%s')
    cmd = 'input text ' + shlex.quote(encoded)
    return adb('shell', cmd, timeout=20)


def is_auth(handler):
    raw = handler.headers.get('Cookie', '')
    c = cookies.SimpleCookie()
    try:
        c.load(raw)
    except Exception:
        return False
    morsel = c.get('takarada_remote')
    return bool(morsel and hmac.compare_digest(morsel.value, COOKIE_VALUE))


def assistant_auth(path):
    q = parse_qs(urlparse(path).query)
    supplied = q.get('token', [''])[0]
    return bool(supplied and hmac.compare_digest(supplied, ASSIST_TOKEN))


PAGE = r'''<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Takarada Secure Phone</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;margin:0;background:#111;color:#eee;text-align:center}
main{max-width:520px;margin:auto;padding:6px}h2{margin:5px 0;font-size:18px}p{font-size:12px;color:#bbb;margin:5px 8px}
#phone{width:auto;max-width:100%;height:min(68vh,640px);aspect-ratio:9/16;object-fit:contain;background:#000;border-radius:12px;touch-action:none;border:1px solid #333}
.controls{position:sticky;bottom:0;background:#111;padding:4px 0 6px}.row{display:flex;gap:6px;justify-content:center;margin:5px 0;flex-wrap:wrap}
button,input{font-size:15px;padding:10px;border-radius:9px;border:1px solid #444;background:#222;color:#fff}
button{min-width:82px}input{width:min(88vw,360px)}#status{min-height:18px;font-size:12px;color:#aaa}
</style></head><body><main>
<h2>Takarada secure phone</h2><p>Temporary direct controller. Text you enter here is sent to the virtual phone runner and is not posted to GitHub.</p>
<img id="phone" src="/screen.jpg?t=0" alt="virtual phone">
<div class="controls"><div id="status">Tap the phone image to interact. Swipe gestures work too.</div>
<div class="row"><button onclick="key('back')">Back</button><button onclick="key('home')">Home</button><button onclick="key('enter')">Enter</button></div>
<div class="row"><input id="txt" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Type password / code privately"></div>
<div class="row"><button onclick="sendText()">Type into phone</button><button onclick="toggle()">Show / hide</button></div></div>
</main><script>
const img=document.getElementById('phone'),st=document.getElementById('status'),txt=document.getElementById('txt');let start=null;
function say(x){st.textContent=x}async function post(path,obj){try{let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj||{})});if(!r.ok)throw new Error(await r.text());say('Sent');setTimeout(refresh,350)}catch(e){say('Error: '+e.message)}}
function coords(ev){const r=img.getBoundingClientRect();return{x:Math.round((ev.clientX-r.left)/r.width*720),y:Math.round((ev.clientY-r.top)/r.height*1280)}}
img.addEventListener('pointerdown',e=>{e.preventDefault();img.setPointerCapture(e.pointerId);start={...coords(e),t:Date.now()}});
img.addEventListener('pointerup',e=>{e.preventDefault();if(!start)return;let q=coords(e),dx=q.x-start.x,dy=q.y-start.y,d=Math.hypot(dx,dy);if(d>45)post('/swipe',{x1:start.x,y1:start.y,x2:q.x,y2:q.y,duration:Math.max(180,Math.min(700,Date.now()-start.t))});else post('/tap',{x:q.x,y:q.y});start=null});
async function sendText(){let v=txt.value;if(!v)return;say('Typing…');await post('/text',{text:v});txt.value=''}function toggle(){txt.type=txt.type==='password'?'text':'password'}function key(k){post('/key',{key:k})}function refresh(){img.src='/screen.jpg?t='+Date.now()}setInterval(refresh,1200);
</script></body></html>'''

LOGIN = r'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Takarada Secure Phone</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:#111;color:#eee;text-align:center;padding:40px 18px}form{max-width:420px;margin:auto}input,button{box-sizing:border-box;width:100%;padding:14px;margin:8px 0;border-radius:10px;border:1px solid #444;background:#222;color:#fff;font-size:17px}p{color:#aaa}</style></head>
<body><form method="POST" action="/login"><h2>Takarada secure phone</h2><p>Enter the temporary access code from ChatGPT.</p><input type="password" name="secret" autocomplete="off" autofocus><button>Open phone</button></form></body></html>'''


class Handler(BaseHTTPRequestHandler):
    server_version = 'TakaradaRemote/1.3'

    def log_message(self, fmt, *args):
        pass

    def send_bytes(self, code, data, ctype='text/plain; charset=utf-8', extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        n = min(int(self.headers.get('Content-Length', '0') or 0), 65536)
        raw = self.rfile.read(n)
        return json.loads(raw or b'{}')

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == '/assistant/screen.png':
            if not assistant_auth(self.path):
                return self.send_bytes(403, b'forbidden')
            return self.send_bytes(200, screenshot(), 'image/png')
        if u.path == '/assistant/screen.txt':
            if not assistant_auth(self.path):
                return self.send_bytes(403, b'forbidden')
            data = screenshot_text()
            if not data:
                return self.send_bytes(503, b'no screenshot')
            return self.send_bytes(200, data, 'text/plain; charset=utf-8')
        if u.path == '/assistant/tap':
            if not assistant_auth(self.path):
                return self.send_bytes(403, b'forbidden')
            try:
                x = max(0, min(719, int(q.get('x', ['0'])[0])))
                y = max(0, min(1279, int(q.get('y', ['0'])[0])))
            except ValueError:
                return self.send_bytes(400, b'bad coordinates')
            adb('shell', 'input', 'tap', str(x), str(y))
            return self.send_bytes(200, b'ok')
        if u.path == '/assistant/swipe':
            if not assistant_auth(self.path):
                return self.send_bytes(403, b'forbidden')
            try:
                vals = [int(q.get(k, ['0'])[0]) for k in ('x1', 'y1', 'x2', 'y2')]
                dur = max(100, min(1500, int(q.get('duration', ['350'])[0])))
            except ValueError:
                return self.send_bytes(400, b'bad swipe')
            adb('shell', 'input', 'swipe', *(str(v) for v in vals), str(dur))
            return self.send_bytes(200, b'ok')
        if u.path == '/assistant/key':
            if not assistant_auth(self.path):
                return self.send_bytes(403, b'forbidden')
            key = q.get('key', [''])[0]
            code = {'back': 'KEYCODE_BACK', 'home': 'KEYCODE_HOME', 'enter': 'KEYCODE_ENTER'}.get(key)
            if not code:
                return self.send_bytes(400, b'bad key')
            adb('shell', 'input', 'keyevent', code)
            return self.send_bytes(200, b'ok')
        if u.path == '/assistant/launch':
            if not assistant_auth(self.path):
                return self.send_bytes(403, b'forbidden')
            app = q.get('app', [''])[0]
            if app == 'tiktok':
                adb('shell', 'monkey', '-p', 'com.zhiliaoapp.musically', '-c', 'android.intent.category.LAUNCHER', '1')
            elif app == 'feed':
                adb('shell', 'am', 'start', '-n', 'com.takarada.display/.MainActivity')
            else:
                return self.send_bytes(400, b'bad app')
            return self.send_bytes(200, b'ok')
        if u.path == '/screen.jpg':
            if not is_auth(self):
                return self.send_bytes(403, b'forbidden')
            return self.send_bytes(200, screenshot(), 'image/png')
        if u.path == '/':
            page = PAGE if is_auth(self) else LOGIN
            return self.send_bytes(200, page.encode(), 'text/html; charset=utf-8')
        return self.send_bytes(404, b'not found')

    def do_POST(self):
        if self.path == '/login':
            n = min(int(self.headers.get('Content-Length', '0') or 0), 8192)
            raw = self.rfile.read(n).decode('utf-8', 'replace')
            supplied = parse_qs(raw).get('secret', [''])[0]
            if not hmac.compare_digest(supplied, SECRET):
                return self.send_bytes(403, b'wrong access code')
            headers = {'Set-Cookie': f'takarada_remote={COOKIE_VALUE}; Path=/; Secure; HttpOnly; SameSite=Strict', 'Location': '/'}
            return self.send_bytes(303, b'', extra=headers)
        if not is_auth(self):
            return self.send_bytes(403, b'forbidden')
        try:
            obj = self.read_json()
        except Exception:
            return self.send_bytes(400, b'bad json')
        if self.path == '/tap':
            x = max(0, min(719, int(obj.get('x', 0))))
            y = max(0, min(1279, int(obj.get('y', 0))))
            adb('shell', 'input', 'tap', str(x), str(y))
        elif self.path == '/swipe':
            vals = [int(obj.get(k, 0)) for k in ('x1', 'y1', 'x2', 'y2')]
            dur = max(100, min(1500, int(obj.get('duration', 350))))
            adb('shell', 'input', 'swipe', *(str(v) for v in vals), str(dur))
        elif self.path == '/text':
            type_text(obj.get('text', ''))
        elif self.path == '/key':
            key = obj.get('key', '')
            code = {'back': 'KEYCODE_BACK', 'home': 'KEYCODE_HOME', 'enter': 'KEYCODE_ENTER'}.get(key)
            if not code:
                return self.send_bytes(400, b'bad key')
            adb('shell', 'input', 'keyevent', code)
        else:
            return self.send_bytes(404, b'not found')
        return self.send_bytes(200, b'ok')


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
