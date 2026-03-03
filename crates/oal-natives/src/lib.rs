//! OMG Natives — Rust acceleration for OMG hot paths.
//!
//! This crate provides high-performance implementations of CPU-intensive
//! operations used by OMG hooks and tools. When compiled and installed,
//! the Python `omg_natives` package will automatically use these native
//! implementations instead of the pure-Python fallbacks.

use pyo3::prelude::*;

pub mod grep;
pub mod shell;
pub mod text;
pub mod keys;
pub mod highlight;
pub mod glob;
pub mod task;
pub mod ps;
pub mod prof;
pub mod image;
pub mod clipboard;
pub mod html;

/// The main Python module entry point.
///
/// When built with `maturin develop` or `maturin build`, this creates
/// the `omg_natives._native` extension module.
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(grep::grep, m)?)?;
    m.add_function(wrap_pyfunction!(glob::glob_match, m)?)?;
    m.add_function(wrap_pyfunction!(text::normalize, m)?)?;
    m.add_function(wrap_pyfunction!(highlight::highlight_syntax, m)?)?;
    m.add_function(wrap_pyfunction!(html::strip_tags, m)?)?;
    Ok(())
}
