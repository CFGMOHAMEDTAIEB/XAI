"""Explicitly lossy image compression for binary PPM (P6) images."""
from __future__ import annotations

import json
import math
import struct
import os
import tempfile
import zlib
from pathlib import Path

import numpy as np
import torch

from .checkpoint import load_checkpoint, model_fingerprint
from .format import pack_container, sha256, unpack_container

QUALITY_STEPS={"low":0.5,"medium":0.25,"high":0.125}
LATENT_HEADER=struct.Struct(">IIIIf")


class LossyCompressionError(ValueError):pass


def read_ppm(data:bytes):
    if not data.startswith(b"P6"):
        raise LossyCompressionError("neural-lossy currently supports binary PPM (P6) images only")
    pos=2;tokens=[]
    while len(tokens)<3:
        while pos<len(data) and data[pos] in b" \t\r\n":pos+=1
        if pos<len(data) and data[pos]==35:
            while pos<len(data) and data[pos] not in b"\r\n":pos+=1
            continue
        start=pos
        while pos<len(data) and data[pos] not in b" \t\r\n":pos+=1
        tokens.append(data[start:pos])
    width,height,maximum=map(int,tokens)
    if maximum!=255 or width<1 or height<1:raise LossyCompressionError("unsupported PPM dimensions/max value")
    while pos<len(data) and data[pos] in b" \t\r\n":pos+=1
    pixels=data[pos:]
    if len(pixels)!=width*height*3:raise LossyCompressionError("PPM pixel length mismatch")
    array=np.frombuffer(pixels,dtype=np.uint8).reshape(height,width,3)
    return array,width,height


def write_ppm(array:np.ndarray)->bytes:
    h,w,c=array.shape
    if c!=3:raise LossyCompressionError("RGB reconstruction required")
    return f"P6\n{w} {h}\n255\n".encode()+array.astype(np.uint8).tobytes()


def compress_lossy_bytes(data:bytes,checkpoint,quality="medium",device="cpu"):
    if quality not in QUALITY_STEPS:raise LossyCompressionError("quality must be low, medium, or high")
    image,w,h=read_ppm(data);model,_=load_checkpoint(checkpoint,device)
    if model.config.architecture_id!="conv-image-autoencoder-v1":raise LossyCompressionError("lossy image checkpoint required")
    x=torch.from_numpy(image.copy()).permute(2,0,1).unsqueeze(0).float().to(device)/255
    with torch.inference_mode():z=model.encode(x)
    step=QUALITY_STEPS[quality];q=torch.round(z/step).clamp(-32768,32767).short().cpu().numpy()
    payload=LATENT_HEADER.pack(w,h,q.shape[1],q.shape[2],step)+zlib.compress(q.tobytes(),9)
    md={"mode":"neural-lossy","lossless":False,"coder_version":"latent-zlib-v1","original_size":len(data),
        "original_sha256":sha256(data),"media_type":"image/x-portable-pixmap","width":w,"height":h,"channels":3,
        "quality":quality,"model_architecture":model.config.architecture_id,"model_fingerprint":model_fingerprint(model)}
    return pack_container(md,payload,format_version=4)


def decompress_lossy_bytes(blob:bytes,checkpoint,device="cpu"):
    md,payload=unpack_container(blob)
    if md.get("mode")!="neural-lossy" or md.get("lossless") is not False:raise LossyCompressionError("not an explicitly lossy artifact")
    model,_=load_checkpoint(checkpoint,device)
    if model_fingerprint(model)!=md.get("model_fingerprint"):raise LossyCompressionError("wrong lossy checkpoint")
    if len(payload)<LATENT_HEADER.size:raise LossyCompressionError("truncated lossy latent")
    w,h,c,lh,step=LATENT_HEADER.unpack_from(payload);raw=zlib.decompress(payload[LATENT_HEADER.size:])
    lw=(w+3)//4;expected=c*lh*lw*2
    if len(raw)!=expected:raise LossyCompressionError("lossy latent length mismatch")
    q=np.frombuffer(raw,dtype=np.int16).reshape(1,c,lh,lw).copy()
    z=torch.from_numpy(q).to(device).float()*step
    with torch.inference_mode():recon=model.decode(z)[...,:h,:w].clamp(0,1)
    pixels=(recon[0].permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8)
    return write_ppm(pixels)


def quality_metrics(original:bytes,reconstructed:bytes):
    a,w,h=read_ppm(original);b,w2,h2=read_ppm(reconstructed)
    if (w,h)!=(w2,h2):raise LossyCompressionError("reconstruction dimensions differ")
    x,y=a.astype(np.float64),b.astype(np.float64);mse=float(np.mean((x-y)**2))
    psnr=float("inf") if mse==0 else 10*math.log10((255**2)/mse)
    mux,muy=x.mean(),y.mean();vx,vy=x.var(),y.var();cov=((x-mux)*(y-muy)).mean();c1=(.01*255)**2;c2=(.03*255)**2
    ssim=((2*mux*muy+c1)*(2*cov+c2))/((mux*mux+muy*muy+c1)*(vx+vy+c2))
    return {"psnr_db":psnr,"ssim":float(ssim),"mse":mse,"width":w,"height":h}


def compress_lossy_file(src:Path,dst:Path,checkpoint,quality="medium",overwrite=False):
    if dst.exists() and not overwrite:raise FileExistsError(dst)
    if not checkpoint:raise LossyCompressionError("neural-lossy requires --checkpoint")
    blob=compress_lossy_bytes(src.read_bytes(),checkpoint,quality);dst.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=dst.name+".",suffix=".tmp",dir=dst.parent)
    try:
        with os.fdopen(fd,"wb") as handle:handle.write(blob);handle.flush();os.fsync(handle.fileno())
        unpack_container(Path(tmp).read_bytes());os.replace(tmp,dst)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {"original_size":src.stat().st_size,"artifact_size":len(blob),"mode":"neural-lossy","lossless":False,"quality":quality,"format_version":4}
