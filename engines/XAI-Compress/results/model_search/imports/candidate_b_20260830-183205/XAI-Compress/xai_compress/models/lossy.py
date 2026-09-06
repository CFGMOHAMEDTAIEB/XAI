from __future__ import annotations

import torch
from torch import nn

from ..model import ModelConfig


class ConvImageAutoencoderV1(nn.Module):
    """Small image-domain autoencoder; quality comes from a quantized latent."""
    def __init__(self, config: ModelConfig):
        super().__init__();self.config=config;c=max(8,int(config.embedding_dim))
        self.encoder=nn.Sequential(nn.Conv2d(3,c,5,2,2),nn.GELU(),nn.Conv2d(c,2*c,5,2,2),nn.GELU(),nn.Conv2d(2*c,c,3,1,1))
        self.decoder=nn.Sequential(nn.ConvTranspose2d(c,2*c,4,2,1),nn.GELU(),nn.ConvTranspose2d(2*c,c,4,2,1),nn.GELU(),nn.Conv2d(c,3,3,1,1),nn.Sigmoid())

    def encode(self,x):return self.encoder(x)
    def decode(self,z):return self.decoder(z)
    def forward(self,x):return self.decode(self.encode(x))
