import os
import subprocess
import time
import socket
import tempfile
from typing import Optional, Dict, Any


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _detect_project_type(project_dir: str) -> str:
    """Detect project type from files present."""
    if os.path.exists(os.path.join(project_dir, "next.config.js")):
        return "nextjs"
    if os.path.exists(os.path.join(project_dir, "vite.config.ts")):
        return "vite"
    if os.path.exists(os.path.join(project_dir, "package.json")):
        with open(os.path.join(project_dir, "package.json")) as f:
            content = f.read()
        if "express" in content:
            return "express"
    if os.path.exists(os.path.join(project_dir, "index.html")):
        return "static"
    return "unknown"


def preview(project_dir: str, timeout_sec: int = 60) -> Dict[str, Any]:
    """Start local preview server and capture screenshot.

    Returns:
        {url: str, screenshot_path: str, project_type: str, server_pid: int}
    """
    project_type = _detect_project_type(project_dir)
    port = _find_free_port()
    url = f"http://localhost:{port}"

    if project_type == "static":
        cmd = ["python3", "-m", "http.server", str(port), "--directory", project_dir]
    else:
        cmd = ["python3", "-m", "http.server", str(port), "--directory", project_dir]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    start = time.time()
    ready = False
    while time.time() - start < timeout_sec:
        try:
            import urllib.request

            urllib.request.urlopen(url, timeout=1)
            ready = True
            break
        except Exception:
            time.sleep(0.5)

    if not ready:
        proc.terminate()
        return {
            "url": url,
            "screenshot_path": None,
            "project_type": project_type,
            "error": "Server timeout",
        }

    screenshot_path = os.path.join(tempfile.gettempdir(), f"omg-preview-{port}.png")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=10000)
            page.screenshot(path=screenshot_path)
            browser.close()
    except Exception:
        screenshot_path = None

    return {
        "url": url,
        "screenshot_path": screenshot_path,
        "project_type": project_type,
        "server_pid": proc.pid,
        "_proc": proc,
    }
