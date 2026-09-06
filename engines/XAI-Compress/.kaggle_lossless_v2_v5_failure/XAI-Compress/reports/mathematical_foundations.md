# Mathematical Foundations

## Source model and lossless coding

For bytes \(X_1,\ldots,X_n\), the chain rule gives

\[
P(x_1,\ldots,x_n)=\prod_{i=1}^{n}P(x_i\mid x_{<i}).
\]

XAI-Compress predicts each conditional distribution over 256 byte values. Arithmetic coding or rANS converts the same deterministic, integer-quantized distributions into bits. The decoder reproduces each distribution from previously decoded bytes, recovers the next byte, and verifies the final SHA-256 digest. The neural network is therefore a probability estimator, not a lossy autoencoder.

## Entropy, conditional entropy, and entropy rate

For a discrete source, \(H(X)=-\sum_x p(x)\log_2p(x)\). Joint entropy describes pairs or sequences; conditional entropy is \(H(X\mid Y)=H(X,Y)-H(Y)\). Mutual information, \(I(X;Y)=H(X)-H(X\mid Y)\), measures how much context can reduce uncertainty. For a stationary process, its entropy rate is \(\lim_{n\to\infty}H(X_n\mid X_{<n})\). An order-zero byte histogram estimates marginal entropy, not this entropy rate; repeated structure may remain compressible even when its histogram appears broad.

## Cross entropy, KL divergence, and coding regret

If the true conditional distribution is \(P\) and the model uses \(Q\), expected coding cost is

\[
H(P,Q)=-\sum_xP(x)\log_2Q(x)=H(P)+D_{KL}(P\Vert Q),
\]

where \(D_{KL}(P\Vert Q)=\sum_xP(x)\log_2(P(x)/Q(x))\). The non-negative KL term is the model's idealized coding regret. Integer frequency quantization and container metadata add further overhead.

Gibbs' inequality states \(D_{KL}(P\Vert Q)\geq0\), with equality only when the distributions agree wherever \(P>0\). Intuitively, incorrect confidence costs bits. Practically, assigning a common byte probability \(1/16\) instead of \(1/2\) costs three extra bits whenever it occurs.

## Training objective and BPB

The token loss in bits is

\[
L=-\sum_i\log_2Q(x_i\mid x_{<i}).
\]

Mean cross entropy in nats divided by \(\ln2\) is predicted bits per byte. Actual container BPB is \(8S_c/S_o\), where \(S_o\) and \(S_c\) are original and compressed byte counts. Compression ratio is \(S_o/S_c\), and saving percentage is \(100(1-S_c/S_o)\). Predicted BPB and artifact BPB differ because of finite precision, coder termination, chunk headers, hashes, and general container metadata.

## Shannon source coding theorem

**Statement.** For an ergodic source, rates above its entropy rate are asymptotically achievable with arbitrarily small error, while reliable rates below it are impossible.

**Intuition.** Typical sequences occupy roughly \(2^{nH}\) possibilities and require roughly \(nH\) binary decisions.

**System relevance.** Better context models can approach conditional entropy but cannot violate the source limit. A random or encrypted stream near 8 BPB cannot be universally compressed.

**Example.** A fair binary source needs one bit per symbol; a source emitting zero with probability 0.99 has entropy about 0.081 bits per symbol and can be coded much more compactly over long sequences.

## Kraft–McMillan inequality

**Statement.** Prefix-code lengths \(l_i\) must satisfy \(\sum_i2^{-l_i}\leq1\), and any integer lengths satisfying it admit a prefix code.

**Intuition.** Codewords consume leaves of a binary tree; short words consume more tree capacity.

**System relevance.** It explains why ideal lengths are approximately \(-\log_2p_i\). Arithmetic coding avoids rounding every symbol to an integer-length prefix word.

**Example.** Two symbols of probabilities 3/4 and 1/4 have ideal lengths 0.415 and 2 bits, but a symbol-by-symbol binary prefix code cannot assign a fractional-length first codeword.

## Data processing inequality

**Statement.** For a Markov chain \(X\to Z\to Y\), \(I(X;Y)\leq I(X;Z)\).

**Intuition.** Processing cannot create information about the original source that was discarded earlier.

**System relevance.** Truncated context, lossy tokenization, or insufficient hidden state can remove predictive information. Byte tokenization is reversible, while bounded context intentionally trades information for speed and memory.

**Example.** Mapping all ASCII letters to one category cannot later recover which letter occurred; a predictor using only that category has less usable context.

## Arithmetic coding

Arithmetic coding repeatedly narrows an interval in proportion to quantized symbol probabilities. A final binary fraction inside the interval represents the sequence. Encoder and decoder must use identical cumulative-frequency tables at every step. Any floating-point or context divergence corrupts the remaining stream, which is why this implementation converts logits to deterministic positive integer frequencies.

## ANS and rANS

ANS represents information in an integer state. rANS updates this state using a symbol's cumulative start and frequency, emitting low-order bytes when normalization bounds are exceeded. Decoding reverses the transformation. Symbols are encoded in reverse state order internally, while the public encoder buffers forward model predictions. With total frequency \(M=2^{14}\), a symbol frequency \(f_s\) has approximate cost \(\log_2(M/f_s)\).

## Limits of the analysis

These results establish correctness relationships and theoretical bounds, not empirical superiority. Dataset entropy estimates, trained cross entropy, and measured artifact sizes must be reported separately. Model weights required outside the container are also a deployment dependency and must be accounted for when comparing standalone storage systems.
