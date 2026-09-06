from __future__ import annotations
import hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path
I=Path('/kaggle/input');W=Path('/kaggle/working');P=W/'XAI-Compress';R=W/'gradient_diagnostic';R.mkdir(exist_ok=True)
s=next((p.parent for p in I.rglob('pyproject.toml') if (p.parent/'xai_compress.zip').is_file() or (p.parent/'xai_compress').is_dir()),None)
if s is None:raise RuntimeError('SOURCE_SNAPSHOT_MISMATCH')
P.mkdir(exist_ok=True)
for item in s.iterdir():
    if item.is_file() and item.suffix=='.zip':
        with zipfile.ZipFile(item) as z:
            ns=[Path(n) for n in z.namelist() if n and not n.endswith('/')];t=P if ns and all(n.parts[0]==item.stem for n in ns) else P/item.stem;t.mkdir(exist_ok=True);z.extractall(t)
    elif item.is_file():shutil.copy2(item,P/item.name)
    elif item.is_dir():shutil.copytree(item,P/item.name,dirs_exist_ok=True)
expected={'xai_compress/models/transformer_v2.py':'5b5ce6851e6a746de7fce01383c444dac10d1cc6c118c5dff15b459d69234ed3',
          'xai_compress/train.py':'318d30819eecebfc27a790db51183c4a00d09587c10808c093e836e39f2dcdb2'}
actual={k:hashlib.sha256((P/k).read_bytes()).hexdigest() for k in expected};print('SOURCE HASHES',json.dumps(actual),flush=True)
if actual!=expected or not (P/'scripts/debug_lossless_v2_gradients.py').is_file():raise RuntimeError('SOURCE_SNAPSHOT_MISMATCH')
subprocess.run([sys.executable,'-m','pip','install','-e',str(P),'--no-deps','--no-build-isolation'],check=True)
import torch;print(json.dumps({'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__,'cuda':torch.version.cuda}),flush=True)
d=I/'ff-c23';d=d if d.is_dir() else next(p for p in I.iterdir() if p!=s and p.is_dir());script=P/'scripts/debug_lossless_v2_gradients.py'
def run(name,amp=True,lr=.001,scale=65536,growth=2000):
    cmd=[sys.executable,'-u',str(script),str(d),'--samples','180000','--learning-rate',str(lr),'--init-scale',str(scale),'--growth-interval',str(growth),'--output',str(R/f'{name}.json'),('--amp' if amp else '--no-amp')]
    print('RUN',name,cmd,flush=True);return subprocess.run(cmd,check=False).returncode
amp=run('amp_baseline')
if amp==0:print('VERSION 5 PRODUCTION = READY baseline AMP',flush=True);raise SystemExit(0)
fp32=run('fp32_replay',False)
if fp32==0:
    print('CLASSIFICATION AMP_GRADIENT_OVERFLOW',flush=True)
    fixed=run('amp_low_scale',True,.001,1024,10000)
    print('VERSION 5 PRODUCTION = '+('READY init_scale=1024 growth_interval=10000' if fixed==0 else 'NOT READY'),flush=True);raise SystemExit(fixed)
print('CLASSIFICATION TRUE_GRADIENT_INSTABILITY',flush=True)
for lr in (.0005,.0003,.0001):
    code=run('amp_lr_'+str(lr),True,lr)
    if code==0:print(f'VERSION 5 PRODUCTION = READY lr={lr}',flush=True);raise SystemExit(0)
print('VERSION 5 PRODUCTION = NOT READY',flush=True);raise SystemExit(1)
