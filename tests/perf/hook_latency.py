#!/usr/bin/env python3
"""
Hook Latency Benchmark Script

Measures execution time for all Python hooks in hooks/ directory.
Runs each hook 3 times with minimal input (empty JSON {}) and records min/avg/max latency.

Usage:
    python3 tests/perf/hook_latency.py

Output:
    .omg/baselines/hook_performance.json
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOOK_LATENCY_AVG_BUDGET_MS = 200.0
RUNTIME_STRESS_LATENCY_BUDGET_MS = 300.0
RUNTIME_STRESS_MEMORY_BUDGET_MB = 128.0


def get_project_dir():
    """Get project directory."""
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def find_hook_files():
    """Find all .py files in hooks/ directory, excluding _common.py and _*.py."""
    project_dir = get_project_dir()
    hooks_dir = os.path.join(project_dir, "hooks")
    
    if not os.path.isdir(hooks_dir):
        print(f"Error: hooks directory not found at {hooks_dir}", file=sys.stderr)
        return []
    
    hook_files = []
    for filename in sorted(os.listdir(hooks_dir)):
        if filename.endswith(".py") and not filename.startswith("_"):
            hook_files.append(filename)
    
    return hook_files


def run_hook(hook_path, timeout_sec=5):
    """
    Run a single hook with empty JSON input.
    
    Returns:
        elapsed_ms (float): Elapsed time in milliseconds, or None on error
        error (str): Error message if hook failed, None otherwise
    """
    try:
        start = time.time()
        
        # Run hook with empty JSON input
        result = subprocess.run(
            ["python3", hook_path],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        
        elapsed = (time.time() - start) * 1000  # Convert to milliseconds
        
        # Record error if exit code is non-zero, but still return timing
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else f"exit code {result.returncode}"
            return elapsed, error_msg
        
        return elapsed, None
    
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout_sec}s"
    except Exception as e:
        return None, str(e)


def benchmark_hook(hook_path, hook_name, runs=3):
    """
    Benchmark a single hook by running it multiple times.
    
    Returns:
        dict: {
            "min_ms": float,
            "avg_ms": float,
            "max_ms": float,
            "status": "ok" | "error",
            "error": str (if status == "error")
        }
    """
    timings = []
    errors = []
    
    for i in range(runs):
        elapsed, error = run_hook(hook_path)
        
        if error:
            errors.append(error)
        else:
            timings.append(elapsed)
    
    # If all runs failed, record as error
    if not timings:
        return {
            "min_ms": None,
            "avg_ms": None,
            "max_ms": None,
            "status": "error",
            "error": errors[0] if errors else "unknown error"
        }
    
    # If some runs failed, still record the successful ones
    return {
        "min_ms": round(min(timings), 2),
        "avg_ms": round(sum(timings) / len(timings), 2),
        "max_ms": round(max(timings), 2),
        "status": "ok" if not errors else "partial_error",
        "error": errors[0] if errors else None
    }


def build_benchmark_payload(project_dir, hooks):
    """Build a deterministic hook latency payload with budget summary."""
    hook_count = len(hooks)
    slowest_hook = ""
    slowest_avg = -1.0
    over_budget = []

    for hook_name, metrics in hooks.items():
        avg_ms = float(metrics.get("avg_ms") or 0.0)
        if avg_ms > slowest_avg:
            slowest_avg = avg_ms
            slowest_hook = hook_name
        if avg_ms > HOOK_LATENCY_AVG_BUDGET_MS:
            over_budget.append(hook_name)

    return {
        "schema": "OmgHookLatencyBaseline",
        "project_dir": project_dir,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "hooks": hooks,
        "budgets": {"max_avg_ms": HOOK_LATENCY_AVG_BUDGET_MS},
        "summary": {
            "hook_count": hook_count,
            "slowest_hook": slowest_hook,
            "over_budget": over_budget,
        },
    }


def build_runtime_stress_budget_payload(project_dir, *, samples, tmux_report):
    """Build a runtime stress payload covering latency, memory, and tmux reuse."""
    over_latency_budget = [
        str(sample.get("name", ""))
        for sample in samples
        if float(sample.get("avg_ms") or 0.0) > RUNTIME_STRESS_LATENCY_BUDGET_MS
    ]
    over_memory_budget = [
        str(sample.get("name", ""))
        for sample in samples
        if float(sample.get("peak_memory_mb") or 0.0) > RUNTIME_STRESS_MEMORY_BUDGET_MB
    ]
    tmux_reuse_within_budget = bool(tmux_report.get("within_budget", False))

    return {
        "schema": "OmgRuntimeStressBudget",
        "project_dir": project_dir,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "samples": list(samples),
        "tmux_report": dict(tmux_report),
        "budgets": {
            "max_avg_ms": RUNTIME_STRESS_LATENCY_BUDGET_MS,
            "max_peak_memory_mb": RUNTIME_STRESS_MEMORY_BUDGET_MB,
        },
        "summary": {
            "sample_count": len(samples),
            "over_latency_budget": over_latency_budget,
            "over_memory_budget": over_memory_budget,
            "tmux_reuse_within_budget": tmux_reuse_within_budget,
            "within_budget": not over_latency_budget and not over_memory_budget and tmux_reuse_within_budget,
        },
    }


def main():
    """Main benchmark runner."""
    project_dir = get_project_dir()
    hooks_dir = os.path.join(project_dir, "hooks")
    
    print(f"[*] Hook Latency Benchmark")
    print(f"[*] Project dir: {project_dir}")
    print(f"[*] Hooks dir: {hooks_dir}")
    
    # Find all hook files
    hook_files = find_hook_files()
    if not hook_files:
        print("Error: No hook files found", file=sys.stderr)
        sys.exit(1)
    
    print(f"[*] Found {len(hook_files)} hooks")
    print()
    
    # Benchmark each hook
    results = {}
    for i, hook_name in enumerate(hook_files, 1):
        hook_path = os.path.join(hooks_dir, hook_name)
        print(f"[{i}/{len(hook_files)}] Benchmarking {hook_name}...", end=" ", flush=True)
        
        result = benchmark_hook(hook_path, hook_name, runs=3)
        results[hook_name] = result
        
        if result["status"] == "ok":
            print(f"✓ {result['avg_ms']}ms (min={result['min_ms']}, max={result['max_ms']})")
        else:
            print(f"✗ {result['error']}")
    
    print()
    
    # Prepare output
    output = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "hooks": results
    }
    
    # Save to .omg/baselines/hook_performance.json
    baseline_dir = os.path.join(project_dir, ".omg", "baselines")
    os.makedirs(baseline_dir, exist_ok=True)
    
    baseline_path = os.path.join(baseline_dir, "hook_performance.json")
    with open(baseline_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"[✓] Baseline saved to {baseline_path}")
    
    # Copy to evidence directory
    evidence_dir = os.path.join(project_dir, ".sisyphus", "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    
    evidence_path = os.path.join(evidence_dir, "task-0-1-baseline.json")
    with open(evidence_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"[✓] Evidence saved to {evidence_path}")
    
    # Print summary
    ok_count = sum(1 for r in results.values() if r["status"] == "ok")
    error_count = sum(1 for r in results.values() if r["status"] == "error")
    partial_count = sum(1 for r in results.values() if r["status"] == "partial_error")
    
    print()
    print(f"Summary: {ok_count} ok, {partial_count} partial, {error_count} error")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
