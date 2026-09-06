import numpy as np
import pytest
import torch

from xai_compress.checkpoint import save_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.format import unpack_container
from xai_compress.lossy import LossyCompressionError, compress_lossy_bytes, decompress_lossy_bytes, quality_metrics, read_ppm
from xai_compress.model import ModelConfig
from xai_compress.models.registry import build_model
from xai_compress.train_lossy import train_lossy


def ppm(width=16,height=12):
    y,x=np.mgrid[:height,:width];rgb=np.stack(((x*13)%256,(y*17)%256,((x+y)*9)%256),axis=-1).astype(np.uint8)
    return f"P6\n{width} {height}\n255\n".encode()+rgb.tobytes()


def checkpoint(tmp_path):
    torch.manual_seed(3);model=build_model(ModelConfig(embedding_dim=8,hidden_dim=8,num_layers=1,context_length=1,
        dropout=0,architecture_id="conv-image-autoencoder-v1"));path=tmp_path/"lossy.pt";save_checkpoint(path,model);return path


def test_lossy_image_roundtrip_metadata_and_metrics(tmp_path):
    ckpt=checkpoint(tmp_path);original=ppm();blob=compress_lossy_bytes(original,ckpt,"medium");md,_=unpack_container(blob)
    assert md["format_version"]==4 and md["mode"]=="neural-lossy" and md["lossless"] is False
    restored=decompress_lossy_bytes(blob,ckpt);a,w,h=read_ppm(restored);assert (w,h)==(16,12)
    metrics=quality_metrics(original,restored);assert np.isfinite(metrics["psnr_db"]);assert -1<=metrics["ssim"]<=1
    assert restored != original


def test_lossy_rejects_unsupported_binary(tmp_path):
    with pytest.raises(LossyCompressionError,match="PPM"):
        compress_lossy_bytes(b"not an image",checkpoint(tmp_path))


def test_lossy_training_smoke_writes_separate_checkpoint(tmp_path):
    data=tmp_path/"images";data.mkdir()
    for i in range(3):(data/f"{i}.ppm").write_bytes(ppm(16,16))
    output=tmp_path/"checkpoints"/"neural_lossy_v1"/"best.pt"
    train_lossy(data,output,epochs=1,batch_size=1,latent_channels=4,crop=16,max_samples=3,device="cpu")
    assert output.is_file() and output.with_suffix(".metrics.csv").is_file()
