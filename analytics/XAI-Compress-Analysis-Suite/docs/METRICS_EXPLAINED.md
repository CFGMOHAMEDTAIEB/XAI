# Metrics Explained

## Lossless correctness

The mandatory condition is:

```text
SHA256(original) == SHA256(decompressed)
```

A codec that fails this condition is excluded from the lossless ranking.

## Compression ratio

```text
original size / compressed size
```

A value greater than 1 means compression. A value below 1 means expansion.

## Space saving

```text
100 × (1 - compressed size / original size)
```

Higher is better. Negative values mean that the artifact is larger than the input.

## Bits per byte

```text
8 × compressed size / original size
```

Lower is better. Raw uncompressed data corresponds to 8 BPB.

## Cross-entropy and estimated BPB

The neural model minimizes next-byte cross-entropy. The estimated ideal coding cost is:

```text
BPB ≈ cross-entropy in nats / ln(2)
```

The actual artifact BPB is normally slightly higher because of header, quantization, and coding overhead.

## Throughput

```text
input MiB / elapsed seconds
```

Higher is better. Compression and decompression must be reported separately.

## Generalization gap

```text
validation loss - training loss
```

A large or increasing positive gap can indicate overfitting.

## Model value

A model can provide value in different ways:
- lower BPB
- higher speed
- better performance on a specialized domain
- deterministic lossless reconstruction
- safer format and integrity validation
- adaptive selection of the best codec

No single metric proves that a system is globally superior.
