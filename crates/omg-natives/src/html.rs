//! HTML parsing and tag stripping.

use pyo3::prelude::*;

/// Strip HTML tags from a string, returning plain text.
#[pyfunction]
pub fn strip_tags(html: &str) -> PyResult<String> {
    // Stub: will use a fast state-machine parser
    Ok(html.to_string())
}

pub fn placeholder() -> &'static str {
    "not implemented"
}
