import sys, json, pathlib
sys.path.append('c:/Users/ss/Desktop/XAI/XAI/engines/XAI-Compress')
from xai_compress.hybrid.selector import HybridSelector
try:
    sel = HybridSelector(model_path='c:/Users/ss/Desktop/XAI/XAI/engines/XAI-Compress/checkpoints/selector_v2/best.json')
    artifact, err = sel._load_artifact()
    print('Loaded', bool(artifact), 'err', err)
    if artifact:
        print('Artifact keys:', artifact.__dict__.keys())
except Exception as e:
    print('Exception', e)
