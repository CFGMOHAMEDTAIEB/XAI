import hashlib

import torch

from xai_compress.checkpoint import load_checkpoint, save_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.model import ModelConfig
from xai_compress.models.registry import build_model
from xai_compress.train import train


def tiny_v2():
    return build_model(ModelConfig(embedding_dim=32,hidden_dim=32,num_layers=2,context_length=32,
        dropout=0.0,architecture_id="causal-byte-transformer-v2",n_heads=4,ff_dim=64))


def test_v2_checkpoint_and_deterministic_steps(tmp_path):
    torch.manual_seed(7);model=tiny_v2().eval();ckpt=tmp_path/"v2.pt";save_checkpoint(ckpt,model)
    loaded,_=load_checkpoint(ckpt,"cpu")
    a,_=loaded.step(256,None);b,_=loaded.step(256,None)
    assert torch.equal(a,b)


def test_v2_exact_lossless_roundtrip(tmp_path):
    torch.manual_seed(8);model=tiny_v2().eval();ckpt=tmp_path/"v2.pt";save_checkpoint(ckpt,model)
    for data in (b"",b"x",b"transformer-v2 exact bytes",bytes(range(64))):
        blob=compress_bytes(data,"neural-lossless",ckpt)
        restored=decompress_bytes(blob,ckpt)
        assert hashlib.sha256(restored).digest()==hashlib.sha256(data).digest()


def test_v2_training_smoke_uses_separate_namespace(tmp_path):
    data=tmp_path/"data";data.mkdir();(data/"a.bin").write_bytes(bytes(range(64))*2);(data/"b.bin").write_bytes(b"v2-training"*20)
    output=tmp_path/"checkpoints"/"neural_lossless_v2"/"best.pt"
    train(data,output,epochs=1,batch_size=2,context_length=16,stride=16,max_samples=16,
          max_bytes_per_file=1024,num_workers=0,embedding_dim=16,hidden_dim=16,num_layers=1,
          dropout=0,architecture="causal-byte-transformer-v2",n_heads=4,ff_dim=32,device="cpu",amp=False)
    loaded,_=load_checkpoint(output,"cpu");assert loaded.config.architecture_id=="causal-byte-transformer-v2"


def test_v2_attention_fp32_stability_path():
    model=tiny_v2().train()
    tokens=torch.randint(0,257,(2,32))
    logits,_=model(tokens)
    assert logits.dtype == torch.float32
    assert torch.isfinite(logits).all()
