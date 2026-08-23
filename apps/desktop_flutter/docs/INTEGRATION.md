# Integration

The desktop executes the local engine as a child process:

```text
python -m xai_compress compress INPUT OUTPUT --mode static --overwrite
python -m xai_compress compress INPUT OUTPUT --mode neural --checkpoint MODEL.pt --overwrite
python -m xai_compress decompress INPUT.xaic OUTPUT --checkpoint MODEL.pt --overwrite
```

The backend integration currently uses:

```text
POST /auth/login
POST /shares/redeem
GET  /history
```

Before distribution, package the engine or export the model to ONNX so users do not install Python manually.
