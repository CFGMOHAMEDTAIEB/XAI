"""Internal scans of staged upload/output files; never accepts public scan paths."""
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import hashlib
import json
import logging
from pathlib import Path
import socket
import struct
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from .config import settings

logger = logging.getLogger('uvicorn.error.security')

@dataclass
class ScanResult:
    status: str = 'unavailable'
    clean: bool = False
    clamav_status: str = 'unavailable'
    clamav_matches: list[str] = field(default_factory=list)
    yara_status: str = 'unavailable'
    yara_matches: list[str] = field(default_factory=list)
    sha256: str = ''
    error: str | None = None

def _reply(sock):
    result = bytearray()
    while len(result) < 8192:
        chunk = sock.recv(1024)
        if not chunk:
            break
        result.extend(chunk)
        if b'\0' in chunk:
            return bytes(result).split(b'\0', 1)[0].decode('utf-8', errors='replace')
    raise OSError('Invalid scanner response')

def _connect(timeout):
    return socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=timeout)

def clamav_scan(path):
    with _connect(settings.security_scan_timeout) as sock:
        sock.sendall(b'zINSTREAM\0')
        with path.open('rb') as source:
            while chunk := source.read(65536):
                sock.sendall(struct.pack('!I', len(chunk)) + chunk)
        sock.sendall(struct.pack('!I', 0))
        reply = _reply(sock)
    if reply == 'stream: OK':
        return 'clean', []
    if reply.startswith('stream: ') and reply.endswith(' FOUND'):
        return 'threat', [reply[8:-6]]
    raise OSError('Scanner did not complete the scan')

@lru_cache(maxsize=4)
def load_yara_rules(configured_path):
    import yara
    path = Path(configured_path).resolve(strict=True)
    files = sorted(p for p in path.iterdir() if p.suffix in ('.yar', '.yara')) if path.is_dir() else [path]
    if not files:
        raise ValueError('No YARA rules configured')
    rules = yara.compile(filepaths={f'rules_{i}': str(p) for i, p in enumerate(files)}, includes=False)
    names = [rule.identifier for rule in rules]
    if not names or len(names) != len(set(names)):
        raise ValueError('Empty or duplicate YARA rules')
    return rules

def configured_rules():
    rules = load_yara_rules(settings.yara_rules_path)
    if settings.app_env == 'production' and any(r.identifier == 'XAI_Synthetic_Security_Test' for r in rules):
        raise ValueError('Synthetic test rules are not production rules')
    return rules

def yara_scan(path):
    matches = configured_rules().match(str(path), timeout=settings.security_scan_timeout)
    return ('threat' if matches else 'clean'), sorted({m.rule for m in matches})

def scan_file(path) -> ScanResult:
    result = ScanResult()
    try:
        path = Path(path).resolve(strict=True)
        if not path.is_relative_to(settings.storage_root) or not path.is_file():
            raise ValueError('File is outside controlled storage')
        with path.open('rb') as source:
            result.sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
    except Exception:
        result.error = 'invalid_scan_target'
        return result
    errors = []
    try:
        result.clamav_status, result.clamav_matches = clamav_scan(path)
    except Exception:
        errors.append('clamav_unavailable')
    try:
        result.yara_status, result.yara_matches = yara_scan(path)
    except Exception:
        errors.append('yara_unavailable')
    result.clean = result.clamav_status == result.yara_status == 'clean'
    result.status = 'clean' if result.clean else ('blocked' if 'threat' in (result.clamav_status, result.yara_status) else 'unavailable')
    result.error = ','.join(errors) or None
    return result

def enforce_scan(path, stage, expected_sha256=None, *, request_id=None, user_id=None, db=None):
    started = time.monotonic()
    result = scan_file(path)
    if expected_sha256 and result.sha256 != expected_sha256:
        result.clean = False
        result.status = 'unavailable'
        result.error = 'staged_file_integrity_mismatch'
    record = {'stage': stage, 'request_id': request_id, 'user_id': user_id,
              'timestamp': datetime.now(timezone.utc).isoformat(),
              'duration_seconds': round(time.monotonic()-started, 6),
              'allowed': result.clean, **asdict(result)}
    logger.info('security_scan %s', json.dumps(record, sort_keys=True))
    if db is not None:
        from .models import AuditEvent
        db.add(AuditEvent(user_id=user_id, action='security.scan', resource=request_id or '',
                         result='allowed' if result.clean else 'blocked',
                         details=json.dumps({k: record[k] for k in ('stage','status','sha256','allowed','timestamp','duration_seconds')})))
        db.commit()
    if result.status == 'blocked':
        raise HTTPException(422, 'File rejected by security policy')
    # Never release unscanned bytes, including when the deployment marks scans optional.
    if not result.clean:
        raise HTTPException(503, 'File security verification unavailable; retry later')
    return result

def scanner_health():
    clamav = 'unavailable'
    yara = 'unavailable'
    try:
        with _connect(2) as sock:
            sock.sendall(b'zPING\0')
            if _reply(sock) == 'PONG':
                clamav = 'operational'
    except Exception:
        pass
    try:
        configured_rules()
        yara = 'operational'
    except Exception:
        pass
    return {'status': 'operational' if clamav == yara == 'operational' else 'unavailable',
            'clamav': clamav, 'yara': yara, 'required': settings.security_scan_required}
