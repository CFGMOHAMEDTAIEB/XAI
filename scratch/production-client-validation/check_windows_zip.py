import zipfile
path = 'E:/GradleCache/xai-desktop-build/xai-windows-20260908-155201.zip'
with zipfile.ZipFile(path) as archive:
    names = [n.replace('\\', '/') for n in archive.namelist()]
    for required in ['xai_compress_desktop.exe','flutter_windows.dll','flutter_secure_storage_windows_plugin.dll','data/app.so','data/icudtl.dat']:
        assert required in names, required
    entry = archive.namelist()[names.index('data/app.so')]
    data = archive.read(entry)
    assert b'https://xai-1-be9s.onrender.com' in data
    assert not any(u in data for u in [b'http://localhost:8000', b'http://127.0.0.1:8000', b'http://10.0.2.2:8000'])
    assert archive.testzip() is None
    print('Windows ZIP integrity, required runtime files and production URL verified;',len(names),'entries')
