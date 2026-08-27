use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::path::Path;
use walkdir::WalkDir;

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
    Ok(())
}
