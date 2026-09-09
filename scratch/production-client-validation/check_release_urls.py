from pathlib import Path
paths = [Path('E:/GradleCache/xai-desktop-build/windows/app.so'), *Path('E:/GradleCache/xai-mobile-build/app/intermediates/flutter/release').glob('*/app.so')]
for path in paths:
    data = path.read_bytes()
    target = b'https://xai-1-be9s.onrender.com'
    local = [url.decode() for url in [b'http://localhost:8000', b'http://127.0.0.1:8000', b'http://10.0.2.2:8000'] if url in data]
    print(str(path), 'production_url_present=', target in data, 'local_fallback_urls=', local)
    assert target in data and not local
