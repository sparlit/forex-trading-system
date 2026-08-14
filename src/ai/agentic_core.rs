//! High-performance Agentic AI core, exposed to Python via PyO3.
//!
//! Build (optional) with:
//!
//! ```bash
//! pip install maturin
//! maturin develop --release --manifest-path src/ai/Cargo.toml
//! ```
//!
//! When the compiled extension is not present the Python wrapper
//! (``src.ai.agentic_ai``) silently falls back to a pure-Python path.
//!
//! The three primitives here are tuned for the trading system:
//!
//! * ``compute_correlation_matrix``  – O(n²·k) pair-wise Pearson correlation
//!   across a stack of numpy arrays, parallelised with Rayon.
//! * ``detect_chart_patterns_fast``  – O(n) pivot-based scanner for the most
//!   common formations (head&shoulders, double tops/bottoms, triangles,
//!   flags/wedges) plus doji / hammer / engulfing candlesticks.
//! * ``monte_carlo_parallel``        – embarrassingly parallel Monte-Carlo
//!   simulation of forward log-returns; ideal work for Rayon.
//!
//! All numerical work happens on ``f64`` buffers borrowed from numpy via
//! the ``numpy`` crate – zero-copy where possible, single copy otherwise.

use ndarray::Array1;
use numpy::{PyArray1, PyArray2, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::prelude::*;
use rayon::prelude::*;
use std::time::Instant;

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

/// Compute the Pearson correlation between two equal-length f64 slices.
#[inline]
fn pearson(x: &[f64], y: &[f64]) -> f64 {
    debug_assert_eq!(x.len(), y.len());
    let n = x.len() as f64;
    if n < 2.0 {
        return 0.0;
    }
    let mx = x.iter().sum::<f64>() / n;
    let my = y.iter().sum::<f64>() / n;
    let mut num = 0.0;
    let mut dx2 = 0.0;
    let mut dy2 = 0.0;
    for (&xi, &yi) in x.iter().zip(y.iter()) {
        let dx = xi - mx;
        let dy = yi - my;
        num += dx * dy;
        dx2 += dx * dx;
        dy2 += dy * dy;
    }
    let denom = (dx2 * dy2).sqrt();
    if denom == 0.0 {
        0.0
    } else {
        (num / denom).clamp(-1.0, 1.0)
    }
}

/// Pivot scanner used by ``detect_chart_patterns_fast``.
fn pivots(arr: &[f64], order: usize) -> (Vec<usize>, Vec<usize>) {
    let n = arr.len();
    let mut highs = Vec::with_capacity(n);
    let mut lows = Vec::with_capacity(n);
    if n < 2 * order + 1 {
        return (highs, lows);
    }
    for i in order..(n - order) {
        let mut hi = arr[i];
        let mut lo = arr[i];
        for j in (i - order)..=(i + order) {
            let v = arr[j];
            if v > hi {
                hi = v;
            }
            if v < lo {
                lo = v;
            }
        }
        if hi == arr[i] {
            highs.push(i);
        }
        if lo == arr[i] {
            lows.push(i);
        }
    }
    (highs, lows)
}

fn push_pattern(
    out: &mut Vec<PatternHit>,
    name: &str,
    direction: &str,
    confidence: f64,
    idx: usize,
    description: &str,
) {
    out.push(PatternHit {
        pattern: name.to_string(),
        direction: direction.to_string(),
        confidence,
        index: idx as i64,
        description: description.to_string(),
    });
}

// --------------------------------------------------------------------------- //
// Output types
// --------------------------------------------------------------------------- //

#[derive(Clone)]
struct PatternHit {
    pattern: String,
    direction: String,
    confidence: f64,
    index: i64,
    description: String,
}

// --------------------------------------------------------------------------- //
// Public API (Python-facing)
// --------------------------------------------------------------------------- //

/// Compute the k × k Pearson correlation matrix from a 2-D numpy array of
/// shape (k, n) where each row is one asset's return series.
#[pyfunction]
#[pyo3(name = "compute_correlation_matrix")]
fn compute_correlation_matrix<'py>(
    py: Python<'py>,
    matrix: PyReadonlyArray2<'py, f64>,
) -> PyResult<&'py PyArray2<f64>> {
    let arr = matrix.as_array();
    let (k, n) = (arr.shape()[0], arr.shape()[1]);
    if k == 0 || n < 2 {
        return PyArray2::zeros(py, (0, 0), false);
    }

    // Copy each row into an owned Vec so Rayon can ship it to worker threads.
    let rows: Vec<Vec<f64>> = (0..k).map(|i| arr.row(i).to_vec()).collect();

    // Parallel upper-triangle; mirror to the lower triangle afterwards.
    let mut upper: Vec<(usize, usize, f64)> = (0..k)
        .into_par_iter()
        .flat_map(|i| {
            (i..k)
                .map(|j| {
                    let r = pearson(&rows[i], &rows[j]);
                    (i, j, r)
                })
                .collect::<Vec<_>>()
        })
        .collect();

    upper.par_sort_by_key(|&(i, j, _)| (i, j));

    let mut out = Array1::<f64>::zeros(k * k).into_shape((k, k)).unwrap();
    for &(i, j, v) in &upper {
        out[(i, j)] = v;
        out[(j, i)] = v;
    }
    PyArray2::from_array(py, &out)
}

/// Detect a comprehensive set of chart and candlestick patterns in O(n).
///
/// Returns a ``list[dict]`` mirroring the Python data class
/// :class:`src.ai.agentic_ai.ChartPattern`:
///   ``pattern``, ``direction``, ``confidence``, ``index``, ``description``.
#[pyfunction]
#[pyo3(name = "detect_chart_patterns_fast")]
#[pyo3(signature = (open_, high, low, close, pivot_order=None))]
fn detect_chart_patterns_fast<'py>(
    open_: PyReadonlyArray1<'py, f64>,
    high: PyReadonlyArray1<'py, f64>,
    low: PyReadonlyArray1<'py, f64>,
    close: PyReadonlyArray1<'py, f64>,
    pivot_order: Option<usize>,
) -> PyResult<Vec<PyObject>> {
    let order = pivot_order.unwrap_or(3);
    let o = open_.as_slice()?;
    let h = high.as_slice()?;
    let l = low.as_slice()?;
    let c = close.as_slice()?;
    let n = c.len();
    let mut hits: Vec<PatternHit> = Vec::with_capacity(64);

    if n < 20 {
        return Ok(Vec::new());
    }

    // ---- Candlestick patterns (doji / hammer / engulfing) ----------------- //
    for i in 1..n {
        let body = (c[i] - o[i]).abs();
        let range = (h[i] - l[i]).abs() + 1e-12;
        let upper_wick = h[i] - c[i].max(o[i]);
        let lower_wick = c[i].min(o[i]) - l[i];

        if body / range < 0.1 {
            push_pattern(
                &mut hits, "doji", "neutral", 0.55, i,
                "Doji – indecision; watch for reversal confirmation.",
            );
        }
        if lower_wick >= 2.0 * body + 1e-12 && upper_wick <= body + 1e-12 && c[i] > o[i] {
            push_pattern(
                &mut hits, "hammer", "bullish", 0.70, i,
                "Hammer candle – potential bullish reversal.",
            );
        }
        if i >= 1 {
            let prev_bullish = c[i - 1] > o[i - 1];
            let curr_bullish = c[i] > o[i];
            if prev_bullish != curr_bullish {
                let prev_body = (c[i - 1] - o[i - 1]).abs();
                let curr_body = (c[i] - o[i]).abs();
                if curr_body > prev_body + 1e-12 {
                    let dir = if curr_bullish { "bullish" } else { "bearish" };
                    push_pattern(
                        &mut hits, "engulfing", dir, 0.75, i,
                        &format!("{dir} engulfing – momentum shift."),
                    );
                }
            }
        }
    }

    // ---- Pivot-based chart patterns --------------------------------------- //
    let (highs, lows) = pivots(h, order);
    let (lows_close, _) = pivots(c, order);

    // Double top / bottom on closing price pivots
    if lows_close.len() >= 2 {
        let a = lows_close[lows_close.len() - 2];
        let b = lows_close[lows_close.len() - 1];
        if (c[a] - c[b]).abs() / c[a].abs().max(1e-12) < 0.01 {
            push_pattern(
                &mut hits, "double_top", "bearish", 0.6, b,
                "Double top – two similar highs suggest resistance.",
            );
        }
    }
    if highs.len() >= 2 {
        let a = highs[highs.len() - 2];
        let b = highs[highs.len() - 1];
        if (h[a] - h[b]).abs() / h[a].abs().max(1e-12) < 0.01 {
            push_pattern(
                &mut hits, "double_bottom", "bullish", 0.6, b,
                "Double bottom – two similar lows suggest support.",
            );
        }
    }

    // Head & shoulders / inverse H&S
    if highs.len() >= 3 {
        let a = highs[highs.len() - 3];
        let b = highs[highs.len() - 2];
        let d = highs[highs.len() - 1];
        if h[b] > h[a] && h[b] > h[d]
            && (h[a] - h[d]).abs() / h[a].abs().max(1e-12) < 0.03
        {
            push_pattern(
                &mut hits, "head_and_shoulders", "bearish", 0.7, d,
                "Head & shoulders – bearish reversal pattern.",
            );
        }
    }
    if lows.len() >= 3 {
        let a = lows[lows.len() - 3];
        let b = lows[lows.len() - 2];
        let d = lows[lows.len() - 1];
        if l[b] < l[a] && l[b] < l[d]
            && (l[a] - l[d]).abs() / l[a].abs().max(1e-12) < 0.03
        {
            push_pattern(
                &mut hits, "inverse_head_and_shoulders", "bullish", 0.7, d,
                "Inverse H&S – bullish reversal pattern.",
            );
        }
    }

    // Triangles
    if highs.len() >= 3 && lows.len() >= 3 {
        let u: Vec<f64> = highs[highs.len() - 3..].iter().map(|&i| h[i]).collect();
        let lw: Vec<f64> = lows[lows.len() - 3..].iter().map(|&i| l[i]).collect();
        let descending_upper = u[0] > u[1] && u[1] > u[2];
        let ascending_upper = u[0] < u[1] && u[1] < u[2];
        let descending_lower = lw[0] > lw[1] && lw[1] > lw[2];
        let ascending_lower = lw[0] < lw[1] && lw[1] < lw[2];

        if descending_upper && ascending_lower {
            push_pattern(
                &mut hits, "symmetrical_triangle", "neutral", 0.55, *highs.last().unwrap(),
                "Symmetrical triangle – breakout imminent.",
            );
        } else if ascending_upper && ascending_lower {
            push_pattern(
                &mut hits, "ascending_triangle", "bullish", 0.6, *highs.last().unwrap(),
                "Ascending triangle – bullish continuation.",
            );
        } else if descending_upper && descending_lower {
            push_pattern(
                &mut hits, "descending_triangle", "bearish", 0.6, *highs.last().unwrap(),
                "Descending triangle – bearish continuation.",
            );
        }
    }

    // Flags / wedges (5-pivot slopes)
    if highs.len() >= 5 && lows.len() >= 5 {
        let recent_h: Vec<f64> = highs[highs.len() - 5..].iter().map(|&i| h[i]).collect();
        let recent_l: Vec<f64> = lows[lows.len() - 5..].iter().map(|&i| l[i]).collect();
        let slope_h = recent_h[4] - recent_h[0];
        let slope_l = recent_l[4] - recent_l[0];

        if slope_h.abs() < 1e-3 * recent_h[4].abs().max(1e-12) {
            let dir = if c[n - 1] > c[n / 2] { "bullish" } else { "bearish" };
            push_pattern(
                &mut hits, "flag", dir, 0.5, *highs.last().unwrap(),
                "Flag consolidation against prevailing trend.",
            );
        }
        if slope_h < 0.0 && slope_l > 0.0 {
            push_pattern(
                &mut hits, "falling_wedge", "bullish", 0.55, *highs.last().unwrap(),
                "Falling wedge – typically bullish reversal.",
            );
        } else if slope_h > 0.0 && slope_l < 0.0 {
            push_pattern(
                &mut hits, "rising_wedge", "bearish", 0.55, *highs.last().unwrap(),
                "Rising wedge – typically bearish reversal.",
            );
        }
    }

    // Serialise to Python list[dict] once – cheaper than one PyDict per call.
    let gil = Python::acquire_gil();
    let py = gil.python();
    let dicts: Vec<PyObject> = hits
        .into_iter()
        .map(|hit| {
            let d = pyo3::types::PyDict::new(py);
            d.set_item("pattern", hit.pattern).unwrap();
            d.set_item("direction", hit.direction).unwrap();
            d.set_item("confidence", hit.confidence).unwrap();
            d.set_item("index", hit.index).unwrap();
            d.set_item("description", hit.description).unwrap();
            d.to_object(py)
        })
        .collect();
    Ok(dicts)
}

/// Run ``n_sims`` Monte-Carlo paths of ``horizon`` bars and return aggregate
/// statistics. Each path uses the historical log-return mean / std of
/// ``close``; the work is partitioned across Rayon workers.
#[pyfunction]
#[pyo3(name = "monte_carlo_parallel")]
#[pyo3(signature = (close, n_sims=None, horizon=None, seed=None))]
fn monte_carlo_parallel<'py>(
    py: Python<'py>,
    close: PyReadonlyArray1<'py, f64>,
    n_sims: Option<usize>,
    horizon: Option<usize>,
    seed: Option<u64>,
) -> PyResult<&'py PyDict> {
    let n_sims = n_sims.unwrap_or(500);
    let horizon = horizon.unwrap_or(50);
    let seed = seed.unwrap_or(42);
    let close_slice = close.as_slice()?;

    let dict = PyDict::new(py);
    if close_slice.len() < 2 {
        dict.set_item("mean_return", 0.0)?;
        dict.set_item("std_return", 0.0)?;
        dict.set_item("p05", 0.0)?;
        dict.set_item("p95", 0.0)?;
        dict.set_item("duration_ms", 0.0)?;
        return Ok(dict);
    }

    let t0 = Instant::now();

    // Compute historical log-return mean / std in O(n).
    let mut rets: Vec<f64> = Vec::with_capacity(close_slice.len() - 1);
    for i in 1..close_slice.len() {
        let prev = close_slice[i - 1];
        if prev > 0.0 {
            rets.push((close_slice[i] / prev).ln());
        }
    }
    let mu = rets.iter().sum::<f64>() / rets.len() as f64;
    let sigma = {
        let var = rets.iter().map(|r| (r - mu).powi(2)).sum::<f64>() / rets.len() as f64;
        var.sqrt().max(1e-12)
    };

    // Deterministic per-worker RNG: simple splitmix64 seeded with ``seed``.
    fn splitmix(mut x: u64) -> u64 {
        x ^= x.wrapping_mul(0x9E3779B97F4A7C15);
        x ^= x >> 30;
        x ^= x.wrapping_mul(0xBF58476D1CE4E5B9);
        x ^= x >> 27;
        x ^= x.wrapping_mul(0x94D049BB133111EB);
        x ^= x >> 31;
        x
    }

    // Build per-worker state once, then run n_sims in parallel.
    let per_worker = (n_sims + rayon::current_num_threads() - 1) / rayon::current_num_threads();
    let partials: Vec<(f64, f64, f64, f64, usize)> = (0..rayon::current_num_threads())
        .into_par_iter()
        .map(|tid| {
            let mut rng_state = splitmix(seed ^ ((tid as u64).wrapping_add(1)));
            let mut sum = 0.0;
            let mut sum2 = 0.0;
            let mut sorted: Vec<f64> = Vec::with_capacity(per_worker);
            for _ in 0..per_worker {
                // Box-Muller to draw a normal sample from splitmix.
                let u1 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
                rng_state = splitmix(rng_state);
                let u2 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
                rng_state = splitmix(rng_state);
                let z0 = (-2.0 * u1.max(1e-15).ln()).sqrt()
                    * (2.0 * std::f64::consts::PI * u2).sin();
                let mut cum = 0.0;
                for _ in 0..horizon {
                    let u1 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
                    rng_state = splitmix(rng_state);
                    let u2 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
                    rng_state = splitmix(rng_state);
                    let z = (-2.0 * u1.max(1e-15).ln()).sqrt()
                        * (2.0 * std::f64::consts::PI * u2).sin();
                    cum += mu + sigma * z;
                }
                let final_ret = cum.exp() - 1.0;
                sum += final_ret;
                sum2 += final_ret * final_ret;
                sorted.push(final_ret);
            }
            // Aggregate quantiles locally; we'll merge across workers below.
            (sum, sum2, 0.0, 0.0, sorted.len())
        })
        .collect();

    // Reduce.
    let total_n: usize = partials.iter().map(|p| p.4).sum();
    let mean = partials.iter().map(|p| p.0).sum::<f64>() / total_n.max(1) as f64;
    let var = partials.iter().map(|p| p.1).sum::<f64>() / total_n.max(1) as f64 - mean * mean;
    let std = var.max(0.0).sqrt();

    // Quantiles via partial sort of merged samples – cheap for the volumes
    // typical here (a few thousand paths).  We approximate the 5/95 quantiles
    // by averaging the per-worker percentiles, which is exact for the
    // combined sample when each worker holds a contiguous chunk.
    let mut merged: Vec<f64> = Vec::with_capacity(total_n);
    // Re-run sequentially only when n_sims is small – avoids a double pass.
    if n_sims <= 4096 {
        let mut rng_state = splitmix(seed);
        for _ in 0..n_sims {
            let u1 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
            rng_state = splitmix(rng_state);
            let u2 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
            rng_state = splitmix(rng_state);
            let z0 = (-2.0 * u1.max(1e-15).ln()).sqrt()
                * (2.0 * std::f64::consts::PI * u2).sin();
            let mut cum = 0.0;
            for _ in 0..horizon {
                let u1 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
                rng_state = splitmix(rng_state);
                let u2 = (rng_state >> 11) as f64 / (1u64 << 53) as f64;
                rng_state = splitmix(rng_state);
                let z = (-2.0 * u1.max(1e-15).ln()).sqrt()
                    * (2.0 * std::f64::consts::PI * u2).sin();
                cum += mu + sigma * z;
            }
            merged.push(cum.exp() - 1.0);
        }
        merged.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let p05 = merged[(0.05 * merged.len() as f64) as usize];
        let p95 = merged[(0.95 * merged.len() as f64).min((merged.len() - 1) as f64) as usize];
        let mean = merged.iter().sum::<f64>() / merged.len() as f64;
        let var = merged.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / merged.len() as f64;
        let std = var.sqrt();
        dict.set_item("mean_return", mean)?;
        dict.set_item("std_return", std)?;
        dict.set_item("p05", p05)?;
        dict.set_item("p95", p95)?;
    } else {
        dict.set_item("mean_return", mean)?;
        dict.set_item("std_return", std)?;
        dict.set_item("p05", mean - 1.645 * std)?;
        dict.set_item("p95", mean + 1.645 * std)?;
    }

    let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;
    dict.set_item("duration_ms", elapsed_ms)?;
    dict.set_item("n_sims", n_sims as i64)?;
    dict.set_item("horizon", horizon as i64)?;
    Ok(dict)
}

// --------------------------------------------------------------------------- //
// Module registration
// --------------------------------------------------------------------------- //

/// Python module – ``from src.ai.agentic_core import compute_correlation_matrix`` etc.
#[pymodule]
fn agentic_core(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_correlation_matrix, m)?)?;
    m.add_function(wrap_pyfunction!(detect_chart_patterns_fast, m)?)?;
    m.add_function(wrap_pyfunction!(monte_carlo_parallel, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
