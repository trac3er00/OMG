"""Test version consistency between package.json and settings.json for v2.0.0-alpha"""
import json
import os


def test_package_json_version():
    """RED: package.json should have version 2.0.0-alpha"""
    with open("package.json") as f:
        pkg = json.load(f)
    assert pkg["version"] == "2.0.0-alpha", f"Expected 2.0.0-alpha, got {pkg['version']}"


def test_settings_json_version():
    """RED: settings.json _omg._version should have version 2.0.0-alpha"""
    with open("settings.json") as f:
        settings = json.load(f)
    assert settings["_omg"]["_version"] == "2.0.0-alpha", \
        f"Expected 2.0.0-alpha, got {settings['_omg']['_version']}"


def test_version_consistency():
    """RED: Both files should have matching versions"""
    with open("package.json") as f:
        pkg = json.load(f)
    with open("settings.json") as f:
        settings = json.load(f)
    
    pkg_version = pkg["version"]
    settings_version = settings["_omg"]["_version"]
    
    assert pkg_version == settings_version, \
        f"Version mismatch: package.json={pkg_version}, settings.json={settings_version}"
    assert pkg_version == "2.0.0-alpha", \
        f"Expected 2.0.0-alpha, got {pkg_version}"
