"""Enforce fully native route maturity for OMC-compat skills."""
from __future__ import annotations

from runtime.compat import ROUTE_MATURITY, build_compat_gap_report


def test_all_route_maturity_is_native():
    assert ROUTE_MATURITY, "route maturity table must not be empty"
    non_native = {route: maturity for route, maturity in ROUTE_MATURITY.items() if maturity != "native"}
    assert not non_native, f"Non-native route maturity detected: {non_native}"


def test_gap_report_contains_no_bridge_skills(tmp_path):
    report = build_compat_gap_report(str(tmp_path))
    assert report["maturity_counts"].get("bridge", 0) == 0
    assert report["bridge_skills"] == []
