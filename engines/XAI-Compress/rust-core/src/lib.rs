use numpy::PyReadonlyArray2;
use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::path::Path;
use walkdir::WalkDir;

const SYMBOLS: usize = 256;

fn entropy_counts(counts: &[u64; SYMBOLS], length: usize) -> f64 {
    if length == 0 { return 0.0; }
    counts.iter().filter(|&&count| count > 0).map(|&count| {
        let probability = count as f64 / length as f64;
        -probability * probability.log2()
    }).sum()
}

/// Bounded byte statistics. Python lends its immutable bytes buffer directly
/// to Rust, so the input is not copied at the language boundary.
#[pyfunction]
fn byte_stats(py: Python<'_>, data: &[u8]) -> PyResult<PyObject> {
    let length = data.len();
    let mut counts = [0_u64; SYMBOLS];
    let mut printable = 0_u64;
    let mut ascii = 0_u64;
    let mut digits = 0_u64;
    let mut whitespace = 0_u64;
    let mut newlines = 0_u64;
    for &value in data {
        counts[value as usize] += 1;
        printable += u64::from(matches!(value, 9 | 10 | 13) || (32..=126).contains(&value));
        ascii += u64::from(value < 128);
        digits += u64::from(value.is_ascii_digit());
        whitespace += u64::from(matches!(value, b' ' | b'\t' | b'\r' | b'\n'));
        newlines += u64::from(value == b'\n');
    }
    let mut longest_run = 0_usize;
    let mut run_total = 0_usize;
    let mut run_count = 0_usize;
    let mut index = 0_usize;
    while index < length {
        let mut end = index + 1;
        while end < length && data[end] == data[index] { end += 1; }
        let run = end - index;
        longest_run = longest_run.max(run);
        if run > 1 { run_total += run; }
        run_count += 1;
        index = end;
    }
    let mut ngrams: HashMap<[u8; 4], usize> = HashMap::new();
    for chunk in data.chunks_exact(4) {
        let key = [chunk[0], chunk[1], chunk[2], chunk[3]];
        *ngrams.entry(key).or_insert(0) += 1;
    }
    let ngram_total: usize = ngrams.values().sum();
    let repeated: usize = ngrams.values().filter(|&&count| count > 1).sum();
    let repetition_score = if ngram_total == 0 { 0.0 } else { repeated as f64 / ngram_total as f64 };
    let repeated_ngram_ratio = if ngram_total == 0 { 0.0 } else { 1.0 - ngrams.len() as f64 / ngram_total as f64 };
    let mut seen: HashSet<[u8; 8]> = HashSet::new();
    let mut lz_matches = 0_usize;
    let mut lz_tested = 0_usize;
    for chunk in data.chunks_exact(8) {
        let key = [chunk[0], chunk[1], chunk[2], chunk[3], chunk[4], chunk[5], chunk[6], chunk[7]];
        lz_tested += 1;
        if !seen.insert(key) { lz_matches += 1; }
    }
    let lz_ratio = if lz_tested == 0 { 0.0 } else { lz_matches as f64 / lz_tested as f64 };
    let mut local_values = Vec::new();
    for window in data.chunks(4096) {
        let mut local_counts = [0_u64; SYMBOLS];
        for &value in window { local_counts[value as usize] += 1; }
        local_values.push(entropy_counts(&local_counts, window.len()));
    }
    if local_values.is_empty() { local_values.push(0.0); }
    let local_mean = local_values.iter().sum::<f64>() / local_values.len() as f64;
    let local_std = (local_values.iter().map(|value| (value - local_mean).powi(2)).sum::<f64>() / local_values.len() as f64).sqrt();
    let local_min = local_values.iter().copied().fold(f64::INFINITY, f64::min);
    let local_max = local_values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let mut delta_counts = [0_u64; SYMBOLS];
    for pair in data.windows(2) { delta_counts[pair[1].wrapping_sub(pair[0]) as usize] += 1; }
    let result = PyDict::new_bound(py);
    result.set_item("counts", counts.to_vec())?;
    result.set_item("entropy", entropy_counts(&counts, length))?;
    result.set_item("printable", printable)?;
    result.set_item("ascii", ascii)?;
    result.set_item("digits", digits)?;
    result.set_item("whitespace", whitespace)?;
    result.set_item("newlines", newlines)?;
    result.set_item("longest_run", longest_run)?;
    result.set_item("run_total", run_total)?;
    result.set_item("run_count", run_count)?;
    result.set_item("repetition_score", repetition_score)?;
    result.set_item("repeated_ngram_ratio", repeated_ngram_ratio)?;
    result.set_item("lz_match_ratio", lz_ratio)?;
    result.set_item("local_entropy_mean", local_mean)?;
    result.set_item("local_entropy_std", local_std)?;
    result.set_item("entropy_gradient", local_max - local_min)?;
    result.set_item("delta_entropy", entropy_counts(&delta_counts, length.saturating_sub(1)))?;
    Ok(result.into_any().unbind())
}

fn quantize_row(row: &[f64], total: u32) -> Result<Vec<u32>, &'static str> {
    let remaining = (total - SYMBOLS as u32) as f64;
    let mut freq = [1_u32; SYMBOLS];
    let mut fractions = [0.0_f64; SYMBOLS];
    let mut used = SYMBOLS as u32;
    for i in 0..SYMBOLS {
        if !row[i].is_finite() || row[i] < 0.0 { return Err("non-finite model probabilities"); }
        let raw = row[i] * remaining;
        let base = raw.floor() as u32;
        freq[i] += base; fractions[i] = raw - base as f64; used += base;
    }
    let mut order: Vec<usize> = (0..SYMBOLS).collect();
    order.sort_by(|a, b| fractions[*b].total_cmp(&fractions[*a]).then(a.cmp(b)));
    for index in order.into_iter().take((total - used) as usize) { freq[index] += 1; }
    let mut cumulative = Vec::with_capacity(SYMBOLS + 1); cumulative.push(0);
    let mut running = 0_u32;
    for value in freq { running += value; cumulative.push(running); }
    if running != total { return Err("frequency quantization error"); }
    Ok(cumulative)
}

/// Deterministic probability quantization matching quant.py exactly.
/// NumPy owns the contiguous input; PyO3 borrows it without another copy.
#[pyfunction]
fn quantize_probabilities_batch(probabilities: PyReadonlyArray2<'_, f64>, total: Option<u32>) -> PyResult<Vec<Vec<u32>>> {
    let total = total.unwrap_or(16_384);
    if total < SYMBOLS as u32 {
        return Err(PyValueError::new_err("total must be at least 256"));
    }
    let view = probabilities.as_array();
    if view.shape()[1] != SYMBOLS {
        return Err(PyValueError::new_err("neural model must output 256 logits"));
    }
    let mut output = Vec::with_capacity(view.shape()[0]);
    for row in view.rows() {
        let slice = row.as_slice().ok_or_else(|| PyValueError::new_err("logits must be contiguous"))?;
        output.push(quantize_row(slice, total).map_err(PyValueError::new_err)?);
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn uniform_quantization_is_valid_and_deterministic() {
        let row = [1.0_f64 / SYMBOLS as f64; SYMBOLS];
        let table = quantize_row(&row, 16_384).unwrap();
        assert_eq!(table.len(), 257);
        assert_eq!(table[0], 0);
        assert_eq!(*table.last().unwrap(), 16_384);
        assert!(table.windows(2).all(|pair| pair[1] > pair[0]));
    }

    #[test]
    fn byte_entropy_matches_uniform_alphabet() {
        let counts = [1_u64; SYMBOLS];
        assert!((entropy_counts(&counts, SYMBOLS) - 8.0).abs() < 1e-12);
        assert_eq!(entropy_counts(&[0_u64; SYMBOLS], 0), 0.0);
    }
}

#[pyfunction]
fn read_block(path: &str, offset: u64, length: usize) -> PyResult<Vec<u8>> {
    let file = File::open(path).map_err(|e| PyIOError::new_err(e.to_string()))?;
    let size = file.metadata().map_err(|e| PyIOError::new_err(e.to_string()))?.len();
    if offset > size || length as u64 > size.saturating_sub(offset) {
        return Err(PyValueError::new_err("requested block exceeds file bounds"));
    }
    let mut reader = BufReader::with_capacity(1024 * 1024, file);
    reader.seek(SeekFrom::Start(offset)).map_err(|e| PyIOError::new_err(e.to_string()))?;
    let mut out = vec![0u8; length];
    reader.read_exact(&mut out).map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(out)
}

#[pyfunction]
fn sha256_file(path: &str, chunk_size: Option<usize>) -> PyResult<String> {
    let file = File::open(path).map_err(|e| PyIOError::new_err(e.to_string()))?;
    let mut reader = BufReader::with_capacity(1024 * 1024, file);
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; chunk_size.unwrap_or(1024 * 1024).max(4096)];
    loop {
        let n = reader.read(&mut buf).map_err(|e| PyIOError::new_err(e.to_string()))?;
        if n == 0 { break; }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

#[pyfunction]
fn scan_files(root: &str) -> PyResult<Vec<(String, u64)>> {
    if !Path::new(root).is_dir() { return Err(PyValueError::new_err("root is not a directory")); }
    let mut files = Vec::new();
    for entry in WalkDir::new(root).follow_links(false).into_iter().filter_map(Result::ok) {
        if entry.file_type().is_file() {
            if let Ok(meta) = entry.metadata() { files.push((entry.path().display().to_string(), meta.len())); }
        }
    }
    files.sort_by(|a,b| a.0.cmp(&b.0));
    Ok(files)
}

#[pymodule]
fn xai_compress_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(byte_stats, m)?)?;
    m.add_function(wrap_pyfunction!(read_block, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_file, m)?)?;
    m.add_function(wrap_pyfunction!(scan_files, m)?)?;
    m.add_function(wrap_pyfunction!(quantize_probabilities_batch, m)?)?;
    Ok(())
}
