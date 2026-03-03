//! Fast glob pattern matching for file discovery.

use pyo3::prelude::*;

/// Match files against a glob pattern starting from a base directory.
#[pyfunction]
pub fn glob_match(pattern: &str, base: &str) -> PyResult<Vec<String>> {
    // Stub: full implementation will use globset crate
    let _ = (pattern, base);
    Ok(Vec::new())
}

pub fn placeholder() -> &'static str {
    "not implemented"
}
