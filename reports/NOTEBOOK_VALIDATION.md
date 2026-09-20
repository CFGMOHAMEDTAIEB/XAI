# Scientific notebook validation

Notebook: `notebooks/XAI_Compress_Model_Analysis.ipynb`

The current campaign's clean-kernel notebook command passed. Structural inspection found 24 cells (14 code, 10 Markdown), no stored error outputs, and no dependency on persisted execution state. The validator executes code cells sequentially without rewriting the notebook.

The notebook covers lossless compression, CR, Saving %, BPB, entropy and causal conditional probability, cross-entropy/ideal code length, SHA-256 integrity, CausalByteGRU and GRU equations, corpus analysis, available training/checkpoint evidence, Selector V2, Top-k, Hybrid V1/V2/V3, Brotli-11, benchmark plots, size/speed trade-offs, paired bootstrap analysis, round-trip correctness, limitations, and a balanced scientific conclusion.

Unavailable loss/BPB or confusion-matrix evidence is explicitly labeled unavailable. No synthetic training curve is generated. Selector classification accuracy is explicitly distinguished from final compression performance. The conclusion correctly states that Brotli-11 has the best aggregate compressed size and decode throughput in the recorded benchmark, while Hybrid V3 Top-3 has much higher recorded encoding throughput.
