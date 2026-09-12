#!/bin/sh
set -eu

python - <<'PY'
import os
import socket
import sys
import time

host = os.environ.get('CLAMAV_HOST', '127.0.0.1')
port = int(os.environ.get('CLAMAV_PORT', '3310'))
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2) as connection:
            connection.sendall(b'zPING\0')
            if connection.recv(16).split(b'\0', 1)[0] == b'PONG':
                break
    except OSError:
        pass
    time.sleep(1)
else:
    print('ClamAV did not become ready; API will not start', file=sys.stderr)
    raise SystemExit(1)
PY

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --timeout-keep-alive 5
