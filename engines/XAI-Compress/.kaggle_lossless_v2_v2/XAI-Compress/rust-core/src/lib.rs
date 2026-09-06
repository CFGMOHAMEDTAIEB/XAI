use numpy::PyReadonlyArray2;
use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::path::Path;
use walkdir::WalkDir;

const SYMBOLS: usize = 256;

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
    m.add_function(wrap_pyfunction!(read_block, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_file, m)?)?;
    m.add_function(wrap_pyfunction!(scan_files, m)?)?;
    m.add_function(wrap_pyfunction!(quantize_probabilities_batch, m)?)?;
    Ok(())
}
