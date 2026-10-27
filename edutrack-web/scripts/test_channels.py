import asyncio
import os
import subprocess
import urllib.request
from urllib.parse import urlsplit

import websockets

BASE_URL = os.getenv("EDUTRACK_BASE_URL", "http://127.0.0.1:8080").rstrip("/")


def check_http_routes():
    for path in ("/salud/", "/static/img/logo.svg"):
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"{path} respondió HTTP {response.status}")
        print(f"HTTP {path}: OK")


async def check_websocket_proxy():
    base = urlsplit(BASE_URL)
    scheme = "wss" if base.scheme == "https" else "ws"
    uri = f"{scheme}://{base.netloc}/ws/llamadas/cola/"
    for origin in (BASE_URL, "https://invalid.example"):
        try:
            async with websockets.connect(uri, origin=origin, open_timeout=10):
                raise RuntimeError(f"El servidor aceptó el origen {origin}.")
        except websockets.exceptions.InvalidStatus as exc:
            if exc.response.status_code != 403:
                raise RuntimeError(
                    f"El origen {origin} respondió HTTP {exc.response.status_code}; se esperaba 403."
                ) from exc
    print("WebSocket a través de nginx: rechaza anónimos y origen ajeno (403)")


def main():
    subprocess.run(
        ["docker", "compose", "exec", "-T", "ws", "python", "manage.py", "check_channel_layer"],
        check=True,
    )
    check_http_routes()
    asyncio.run(check_websocket_proxy())


if __name__ == "__main__":
    main()
