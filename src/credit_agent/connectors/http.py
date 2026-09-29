import json
import urllib.request

from .. import config

UA = {"User-Agent": "Mozilla/5.0 (credit-agent-poc)"}


def get_bytes(url, headers=None):
    req = urllib.request.Request(url, headers=dict(UA, **(headers or {})))
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
        return r.read()


def get_json(url, headers=None):
    return json.loads(get_bytes(url, headers).decode("utf-8"))
