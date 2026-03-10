from __future__ import annotations

import json
from urllib.request import Request, urlopen


DEFAULT_HEADERS = {
    "User-Agent": "job-search/0.1 (+local-first tracker)",
    "Accept": "application/json",
}


def fetch_json(url: str) -> dict | list:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


def post_json(url: str, payload: dict) -> dict | list:
    request = Request(
        url,
        headers={**DEFAULT_HEADERS, "Content-Type": "application/json"},
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))
