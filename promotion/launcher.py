#!/usr/bin/env python3
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

import run as engine


def call_publisher(promo_tag, expected_target):
    url = f"https://rubys-realm.vercel.app/api/buffer-status?promo_tag={quote(promo_tag)}"
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
        # The workflow itself runs hourly. One failed attempt is enough for this cycle;
        # hammering a rate-limited publisher only delays recovery.
        raise RuntimeError(f'promotion publish deferred to next hourly cycle: {exc}') from exc


engine.call_publisher = call_publisher
engine.main()
