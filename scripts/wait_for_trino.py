#!/usr/bin/env python3
"""Wait for Trino and the Iceberg catalog before running the lab."""

import json
import time
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8080"
deadline = time.monotonic() + 600

while time.monotonic() < deadline:
    try:
        with urlopen(base + "/v1/info", timeout=5) as response:
            info = json.load(response)
        if info.get("starting", True):
            print("Trino is still starting", flush=True)
        else:
            print("Trino API ready", flush=True)
            break
    except Exception as exc:
        print("Waiting for Trino:", str(exc)[:150], flush=True)
    time.sleep(5)
else:
    raise SystemExit("Trino did not start within 10 minutes")

# проверяем наличие каталога до создания таблиц
for _ in range(30):
    try:
        with urlopen(Request(base + "/v1/info"), timeout=5):
            pass
        break
    except Exception:
        time.sleep(2)
print("Starting SQL checks", flush=True)
