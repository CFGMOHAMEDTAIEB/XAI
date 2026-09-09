"""Read-only scanner diagnostics. Run inside the backend: python security/diagnose_scanners.py.
Only scanner configuration is emitted; never dump the environment or Settings.
"""
import hashlib
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import security_scanner as scanner
from app.config import settings


def diagnose():
    path = Path(settings.yara_rules_path)
    report = {
        'APP_ENV': settings.app_env,
        'CLAMAV_HOST': settings.clamav_host,
        'CLAMAV_PORT': settings.clamav_port,
        'SECURITY_SCAN_REQUIRED': settings.security_scan_required,
        'YARA_RULES_PATH': str(path),
        'yara_path_exists': path.exists(),
    }
    try:
        socket.getaddrinfo(settings.clamav_host, settings.clamav_port, type=socket.SOCK_STREAM)
        report['clamav_dns'] = 'resolved'
    except OSError as exc:
        report['clamav_dns'] = 'unavailable'
        report['clamav_dns_error_type'] = type(exc).__name__
    try:
        with scanner._connect(2) as connection:
            connection.sendall(b'zPING\0')
            report['clamav_ping'] = scanner._reply(connection) == 'PONG'
    except OSError as exc:
        report['clamav_ping'] = False
        report['clamav_connection_error_type'] = type(exc).__name__
    try:
        files = sorted(p for p in path.iterdir() if p.suffix in ('.yar', '.yara')) if path.is_dir() else [path]
        report['yara_rule_file_count'] = len(files)
        rules = scanner.configured_rules()
        report['yara_compile'] = 'pass'
        report['yara_rule_count_including_private'] = len(list(rules))
        report['yara_files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    except Exception as exc:
        report['yara_compile'] = 'fail'
        report['yara_error_type'] = type(exc).__name__
    report['health'] = scanner.scanner_health()
    return report


if __name__ == '__main__':
    print(json.dumps(diagnose(), indent=2, sort_keys=True))
