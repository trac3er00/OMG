//! Syntax highlighting for code snippets.

use pyo3::prelude::*;

/// Highlight source code with ANSI escape codes.
#[pyfunction]
pub fn highlight_syntax(code: &str, language: &str) -> PyResult<String> {
    // Stub: will use tree-sitter or syntect for fast highlighting
    let _ = language;
    Ok(code.to_string())
}

pub fn placeholder() -> &'static str {
    "not implemented"
}
