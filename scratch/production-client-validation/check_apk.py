import zipfile
path = 'E:/GradleCache/xai-mobile-build/app/outputs/flutter-apk/app-release.apk'
with zipfile.ZipFile(path) as apk:
    for name in apk.namelist():
        if name.endswith('/libapp.so'):
            data = apk.read(name)
            assert b'https://xai-1-be9s.onrender.com' in data
            assert not any(u in data for u in [b'http://localhost:8000', b'http://127.0.0.1:8000', b'http://10.0.2.2:8000'])
            print(name, 'production URL verified, no development fallback URLs')
