import hashlib

import torch
import pytest

from xai_compress.checkpoint import load_checkpoint, save_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.model import ModelConfig
from xai_compress.models.registry import build_model
from xai_compress.train import train
from xai_compress.train import (
    _grad_scaler,
    require_finite,
    require_finite_gradients,
    require_finite_optimizer_state,
)
from xai_compress.models.transformer_v2 import _rope


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
          dropout=0,architecture="causal-byte-transformer-v2",n_heads=4,ff_dim=32,device="cpu",amp=False,
          numerical_debug=True)
    loaded,_=load_checkpoint(output,"cpu");assert loaded.config.architecture_id=="causal-byte-transformer-v2"
    history=__import__("json").loads(output.with_suffix(".history.json").read_text())
    assert history[0]["max_activation_layer_0"] > 0
    for field in (
        "gradient_norm_epoch_max", "gradient_abs_max", "parameter_abs_max",
        "optimizer_state_abs_max", "logits_abs_max", "embedding_parameter_abs_max",
        "block_0_block_input_rms", "block_0_attention_output_rms",
        "block_0_residual_attention_rms", "block_0_ffn_normalized_input_rms",
        "block_0_ffn_gated_product_rms", "block_0_ffn_output_rms",
        "block_0_residual_ffn_rms", "block_0_activation_abs_max",
    ):
        assert field in history[0]
        assert history[0][field] >= 0


def test_v2_attention_fp32_stability_path():
    model=tiny_v2().train()
    tokens=torch.randint(0,257,(2,32))
    logits,_=model(tokens)
    assert logits.dtype == torch.float32
    assert torch.isfinite(logits).all()


def test_v2_dropout_rescale_uses_fp32_residual_dtype_under_autocast():
    model=tiny_v2().train();observed={}
    model.activation_observer=lambda stage,value,layer: observed.setdefault((layer,stage),value.dtype)
    with torch.autocast("cpu",dtype=torch.float16):
        logits,_=model(torch.randint(0,257,(2,32)))
    assert observed[(0,"ffn_output")] == torch.float16
    assert observed[(0,"ffn_dropout")] == torch.float32
    assert observed[(0,"residual_ffn")] == torch.float32
    assert logits.dtype == torch.float16


def test_v2_debug_graph_and_mask_are_finite():
    model=tiny_v2().train();model.numerical_debug=True
    logits,_=model(torch.randint(0,257,(2,32)))
    loss=torch.nn.functional.cross_entropy(logits.flatten(0,1),torch.randint(0,256,(64,)))
    loss.backward()
    assert torch.isfinite(logits).all() and torch.isfinite(loss)
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())


def test_v2_rotary_and_fail_fast():
    x=torch.randn(2,4,32,8);out=_rope(x,torch.arange(32));assert torch.isfinite(out).all()
    with pytest.raises(FloatingPointError,match="FIRST NON-FINITE STAGE = validation loss"):
        require_finite(torch.tensor(float("nan")),"validation loss",1,7)


def test_non_finite_output_gradient_detection():
    model = tiny_v2()
    model.output.weight.grad = torch.zeros_like(model.output.weight)
    model.output.weight.grad[0, 0] = float("nan")
    with pytest.raises(FloatingPointError, match=r"gradient:output\.weight"):
        require_finite_gradients(model, epoch=4, step=24024)


def test_non_finite_optimizer_state_detection():
    model = tiny_v2()
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
    logits, _ = model(torch.randint(0, 257, (2, 8)))
    logits.sum().backward(); optimizer.step()
    state = next(iter(optimizer.state.values()))
    state["exp_avg"].view(-1)[0] = float("inf")
    with pytest.raises(FloatingPointError, match="optimizer:0:exp_avg"):
        require_finite_optimizer_state(optimizer, epoch=1, step=1)


def test_grad_scaler_configuration_is_persistable(monkeypatch):
    captured = {}
    class FakeScaler:
        def __init__(self, device, **kwargs):
            captured.update(device=device, **kwargs)
    monkeypatch.setattr(torch.amp, "GradScaler", FakeScaler)
    _grad_scaler(True, initial_scale=1024, growth_interval=10000)
    assert captured == {
        "device": "cuda", "enabled": True, "init_scale": 1024.0,
        "growth_interval": 10000,
    }


def test_v2_resume_preserves_multi_epoch_history(tmp_path):
    data=tmp_path/"data";data.mkdir()
    (data/"a.bin").write_bytes(bytes(range(64))*2)
    (data/"b.bin").write_bytes(b"resume-history"*20)
    output=tmp_path/"best.pt"
    kwargs=dict(batch_size=2,context_length=16,stride=16,max_samples=16,
        max_bytes_per_file=1024,num_workers=0,embedding_dim=16,hidden_dim=16,
        num_layers=1,dropout=0,architecture="causal-byte-transformer-v2",n_heads=4,
        ff_dim=32,device="cpu",amp=False,numerical_debug=True,early_stopping_patience=5)
    train(data,output,epochs=1,**kwargs)
    latest=output.with_name("best.latest.pt")
    train(data,output,epochs=2,resume=latest,**kwargs)
    history=__import__("json").loads(output.with_suffix(".history.json").read_text())
    assert [row["epoch"] for row in history] == [1,2]
    loaded,obj=load_checkpoint(latest,"cpu")
    assert loaded.config.architecture_id=="causal-byte-transformer-v2" and obj["epoch"]==2


def test_v2_resume_discovers_attached_latest_companion_history(tmp_path):
    data=tmp_path/"data";data.mkdir()
    (data/"a.bin").write_bytes(bytes(range(64))*2)
    (data/"b.bin").write_bytes(b"attached-resume"*20)
    attached=tmp_path/"input"/"best.pt";attached.parent.mkdir()
    kwargs=dict(batch_size=2,context_length=16,stride=16,max_samples=16,max_bytes_per_file=1024,
        num_workers=0,embedding_dim=16,hidden_dim=16,num_layers=1,dropout=0,
        architecture="causal-byte-transformer-v2",n_heads=4,ff_dim=32,device="cpu",amp=False,
        numerical_debug=True,early_stopping_patience=5)
    train(data,attached,epochs=1,**kwargs)
    output=tmp_path/"working"/"lossless_v2.pt"
    train(data,output,epochs=2,resume=attached.with_name("best.latest.pt"),**kwargs)
    history=__import__("json").loads(output.with_suffix(".history.json").read_text())
    assert [row["epoch"] for row in history] == [1,2]
