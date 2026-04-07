"""Optional 1-click deploy integration for demo UX.

Detects available platform CLIs on PATH and deploys generated projects.
No credentials are stored; deploy() must be called explicitly.
"""

import re
import shutil
import subprocess

PLATFORMS = {
    "vercel": {"cli": "vercel", "command": ["vercel", "deploy", "--prod", "--yes"]},
    "netlify": {"cli": "netlify", "command": ["netlify", "deploy", "--prod"]},
    "cloudflare": {
        "cli": "wrangler",
        "command": ["wrangler", "pages", "publish", "."],
    },
}


def detect_available_platforms() -> list[str]:
    available = []
    for platform, config in PLATFORMS.items():
        if shutil.which(config["cli"]):
            available.append(platform)
    return available


def deploy(project_dir: str, platform: str = None) -> dict:
    """Deploy to platform. If no platform specified, auto-detect first available.

    Returns:
        dict with keys: deployed, platform, url, available_platforms, message
    """
    available = detect_available_platforms()

    if not available:
        return {
            "deployed": False,
            "platform": None,
            "url": None,
            "available_platforms": [],
            "message": (
                "No deploy CLI found. Install one: "
                "npm i -g vercel  OR  npm i -g netlify-cli"
            ),
        }

    target = platform or available[0]
    if target not in available:
        return {
            "deployed": False,
            "platform": target,
            "url": None,
            "available_platforms": available,
            "message": f"{target} CLI not found. Available: {available}",
        }

    config = PLATFORMS[target]
    try:
        result = subprocess.run(
            config["command"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            url = _extract_url(result.stdout, target)
            return {
                "deployed": True,
                "platform": target,
                "url": url,
                "available_platforms": available,
                "message": "Deployed successfully",
            }
        else:
            return {
                "deployed": False,
                "platform": target,
                "url": None,
                "available_platforms": available,
                "message": result.stderr,
            }
    except subprocess.TimeoutExpired:
        return {
            "deployed": False,
            "platform": target,
            "url": None,
            "available_platforms": available,
            "message": "Deploy timed out",
        }


def _extract_url(output: str, platform: str) -> str | None:
    urls = re.findall(r"https?://[^\s]+", output)
    return urls[0] if urls else None
