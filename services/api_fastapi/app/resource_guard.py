"""Single-process admission and streaming upload bounds, before multipart parsing."""
import asyncio
import logging
import shutil
import tempfile
import time
from fastapi import HTTPException
from starlette.responses import JSONResponse
from .config import settings

logger = logging.getLogger(__name__)

def cleanup_work(path):
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.error('temporary_cleanup_failed')
        # Never expose the filesystem path or return a rejected file.

class ResourceGuard:
    def __init__(self, app):
        self.app = app
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') not in ('/compression/jobs', '/compression/decompress'):
            return await self.app(scope, receive, send)
        async def reject(code, message):
            await JSONResponse({'detail': message}, status_code=code)(scope, receive, send)
        if self.active >= settings.max_heavy_requests:
            return await reject(503, 'Processing capacity unavailable; retry later')
        limit = settings.max_upload_bytes + 1048576  # bounded multipart overhead
        headers = dict(scope.get('headers', []))
        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0: raise ValueError()
        except ValueError:
            return await reject(400, 'Invalid request length')
        if length > limit:
            return await reject(413, 'Upload too large')
        # Reserve pessimistically for all admitted requests, including spool, XAIC and output.
        reserve = settings.min_free_disk_bytes + settings.max_heavy_requests * (
            3 * settings.max_upload_bytes + settings.max_decompressed_bytes + 1048576)
        try:
            if min(shutil.disk_usage(settings.storage_root).free,
                   shutil.disk_usage(tempfile.gettempdir()).free) < reserve:
                return await reject(503, 'Temporary storage capacity unavailable; retry later')
        except OSError:
            return await reject(503, 'Temporary storage capacity unavailable; retry later')
        self.active += 1
        total = 0
        deadline = time.monotonic() + settings.upload_total_timeout
        violation = None
        sent = False
        async def bounded_receive():
            nonlocal total, violation
            try:
                timeout = min(settings.upload_idle_timeout, deadline-time.monotonic())
                if timeout <= 0: raise asyncio.TimeoutError()
                message = await asyncio.wait_for(receive(), timeout)
            except asyncio.TimeoutError:
                violation = (408, 'Upload timed out')
                raise HTTPException(*violation)
            total += len(message.get('body', b''))
            if total > limit:
                violation = (413, 'Upload too large')
                raise HTTPException(*violation)
            return message
        async def safe_send(message):
            nonlocal sent
            if violation:
                if not sent:
                    sent = True
                    await reject(*violation)
                return
            await send(message)
        try:
            await self.app(scope, bounded_receive, safe_send)
        except HTTPException:
            if not violation: raise
            if not sent: await reject(*violation)
        finally:
            self.active -= 1
