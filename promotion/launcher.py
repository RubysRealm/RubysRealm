#!/usr/bin/env python3
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

import run as engine


def call_publisher(promo_tag, expected_target):
    url = f"https://rubys-realm.vercel.app/api/buffer-status?promo_tag={quote(promo_tag)}"
    last = None
    for attempt in range(10):
        try:
            with urlopen(url, timeout=90) as r:
                data = json.loads(r.read().decode())
            if not data.get('ok'):
                raise RuntimeError(json.dumps(data))
            actual = str(data.get('channelName') or '').lstrip('@').lower()
            if actual != expected_target:
                raise RuntimeError(f'wrong promotion target: {actual}')
            return data
        except (HTTPError, URLError, RuntimeError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(20 + attempt * 10)
    raise RuntimeError(f'promotion publish failed after retries: {last}')


engine.call_publisher = call_publisher
engine.main()
