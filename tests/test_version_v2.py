"""Test version consistency between package.json and settings.json."""
import json
import os

from runtime.adoption import CANONICAL_VERSION


def test_package_json_version():
    """package.json should have version matching CANONICAL_VERSION."""
    with open("package.json") as f:
        pkg = json.load(f)
    assert pkg["version"] == CANONICAL_VERSION, f"Expected {CANONICAL_VERSION}, got {pkg['version']}"


def test_settings_json_version():
    """settings.json _omg._version should have version matching CANONICAL_VERSION."""
    with open("settings.json") as f:
        settings = json.load(f)
    assert settings["_omg"]["_version"] == CANONICAL_VERSION, \
        f"Expected {CANONICAL_VERSION}, got {settings['_omg']['_version']}"


def test_version_consistency():
    """Both files should have matching versions."""
    with open("package.json") as f:
        pkg = json.load(f)
    with open("settings.json") as f:
        settings = json.load(f)

    pkg_version = pkg["version"]
    settings_version = settings["_omg"]["_version"]

    assert pkg_version == settings_version, \
        f"Version mismatch: package.json={pkg_version}, settings.json={settings_version}"
    assert pkg_version == CANONICAL_VERSION, \
        f"Expected {CANONICAL_VERSION}, got {pkg_version}"
