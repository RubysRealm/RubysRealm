#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LABEL = b'rubyclips-youtube-auth-v1\x00'


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def unb64u(text: str) -> bytes:
    text = text.strip()
    text += '=' * (-len(text) % 4)
    return base64.urlsafe_b64decode(text)


def root_key() -> bytes:
    raw = os.environ.get('RUBYCLIPS_ROOT_KEY', '').strip()
    if not raw:
        raise SystemExit('RUBYCLIPS_ROOT_KEY is missing')
    try:
        decoded = unb64u(raw)
    except Exception as e:
        raise SystemExit(f'RUBYCLIPS_ROOT_KEY is not valid base64url: {e}')
    if len(decoded) < 24:
        raise SystemExit('RUBYCLIPS_ROOT_KEY is unexpectedly short')
    return hashlib.sha256(LABEL + decoded).digest()


def encrypt(cookie_path: Path, ua_path: Path, out_path: Path):
    cookies = cookie_path.read_text(encoding='utf-8')
    if 'youtube.com' not in cookies:
        raise SystemExit('No YouTube cookies found')
    ua = ua_path.read_text(encoding='utf-8').strip()
    payload = json.dumps({
        'version': 1,
        'cookies': cookies,
        'userAgent': ua,
    }, separators=(',', ':')).encode()
    nonce = os.urandom(12)
    ct = AESGCM(root_key()).encrypt(nonce, payload, b'rubyclips-youtube-auth')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(f'v1.{b64u(nonce)}.{b64u(ct)}\n', encoding='utf-8')


def decrypt(in_path: Path, cookie_path: Path, ua_path: Path):
    packed = in_path.read_text(encoding='utf-8').strip()
    parts = packed.split('.')
    if len(parts) != 3 or parts[0] != 'v1':
        raise SystemExit('Invalid Rubaradaclips auth state')
    nonce = unb64u(parts[1])
    ct = unb64u(parts[2])
    raw = AESGCM(root_key()).decrypt(nonce, ct, b'rubyclips-youtube-auth')
    data = json.loads(raw)
    cookies = str(data.get('cookies') or '')
    ua = str(data.get('userAgent') or '').strip()
    if 'youtube.com' not in cookies or not ua:
        raise SystemExit('Decrypted auth state is incomplete')
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(cookies, encoding='utf-8')
    ua_path.write_text(ua + '\n', encoding='utf-8')
    os.chmod(cookie_path, 0o600)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('encrypt')
    e.add_argument('--cookies', required=True)
    e.add_argument('--ua', required=True)
    e.add_argument('--out', required=True)
    d = sub.add_parser('decrypt')
    d.add_argument('--infile', required=True)
    d.add_argument('--cookies', required=True)
    d.add_argument('--ua', required=True)
    a = p.parse_args()
    if a.cmd == 'encrypt':
        encrypt(Path(a.cookies), Path(a.ua), Path(a.out))
    else:
        decrypt(Path(a.infile), Path(a.cookies), Path(a.ua))


if __name__ == '__main__':
    main()
