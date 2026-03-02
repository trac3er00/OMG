#!/usr/bin/env python3
"""
Fetch Claude rate limits from Anthropic OAuth API and cache for HUD.

Reads OAuth credentials from:
- macOS: Keychain "Claude Code-credentials" (format: {claudeAiOauth: {...}})
- Linux/fallback: ~/.claude/.credentials.json

Caches to: ~/.claude/plugins/oh-my-claudecode/.usage-cache.json
"""

import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def get_claude_config_dir():
    """Get Claude config directory."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def get_cache_path():
    """Get cache file path."""
    return get_claude_config_dir() / "plugins" / "oh-my-claudecode" / ".usage-cache.json"


def read_credentials_from_keychain():
    """Read OAuth credentials from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            # Claude Code stores credentials under 'claudeAiOauth' key
            if "claudeAiOauth" in data:
                return data["claudeAiOauth"]
            return data
    except Exception:
        pass
    return None


def read_credentials_from_file():
    """Read OAuth credentials from file."""
    creds_path = get_claude_config_dir() / ".credentials.json"
    try:
        if creds_path.exists():
            data = json.loads(creds_path.read_text())
            # Handle nested format if present
            if "claudeAiOauth" in data:
                return data["claudeAiOauth"]
            return data
    except Exception:
        pass
    return None


def read_credentials():
    """Read OAuth credentials from keychain or file."""
    # Try keychain first (macOS)
    creds = read_credentials_from_keychain()
    if creds and creds.get("accessToken"):
        return creds
    
    # Fall back to file
    creds = read_credentials_from_file()
    if creds and creds.get("accessToken"):
        return creds
    
    return None


def fetch_usage(credentials):
    """Fetch usage from Anthropic API."""
    access_token = credentials.get("accessToken")
    if not access_token:
        return None
    
    # Create HTTPS request
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": "oauth-2025-04-20",  # Required for OAuth API access
            "Accept": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            
            # Parse response into RateLimits format
            rate_limits = {}
            
            # Five hour (session) limit - API returns percentage 0-100 directly
            five_hour = data.get("five_hour", {})
            if five_hour and "utilization" in five_hour:
                rate_limits["fiveHourPercent"] = float(five_hour["utilization"])
                if five_hour.get("resets_at"):
                    rate_limits["fiveHourResetsAt"] = five_hour["resets_at"]
            
            # Seven day (weekly) limit - API returns percentage 0-100 directly
            seven_day = data.get("seven_day", {})
            if seven_day and "utilization" in seven_day:
                rate_limits["weeklyPercent"] = float(seven_day["utilization"])
                if seven_day.get("resets_at"):
                    rate_limits["weeklyResetsAt"] = seven_day["resets_at"]
            
            # Per-model quotas
            sonnet = data.get("seven_day_sonnet", {})
            if sonnet and "utilization" in sonnet:
                rate_limits["sonnetWeeklyPercent"] = float(sonnet["utilization"])
                if sonnet.get("resets_at"):
                    rate_limits["sonnetWeeklyResetsAt"] = sonnet["resets_at"]
            
            opus = data.get("seven_day_opus", {})
            if opus and "utilization" in opus:
                rate_limits["opusWeeklyPercent"] = float(opus["utilization"])
                if opus.get("resets_at"):
                    rate_limits["opusWeeklyResetsAt"] = opus["resets_at"]
            
            return rate_limits
            
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token expired or invalid
            pass
        return None
    except Exception:
        return None


def write_cache(rate_limits):
    """Write rate limits to cache file."""
    cache_path = get_cache_path()
    cache_dir = cache_path.parent
    
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        cache_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": rate_limits,
            "source": "anthropic"
        }
        
        # Write to temp file then rename for atomicity
        temp_path = cache_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(cache_data, indent=2))
        temp_path.rename(cache_path)
        
        return True
    except Exception:
        return False


def read_existing_cache():
    """Read existing cache if present."""
    cache_path = get_cache_path()
    try:
        if cache_path.exists():
            return json.loads(cache_path.read_text())
    except Exception:
        pass
    return None


def main():
    """Main entry point."""
    # Check if cache is fresh (less than 30 seconds old)
    existing = read_existing_cache()
    if existing:
        try:
            cached_time = datetime.fromisoformat(existing.get("timestamp", ""))
            age = (datetime.now(timezone.utc) - cached_time).total_seconds()
            if age < 30:
                # Cache is fresh, nothing to do
                sys.exit(0)
        except Exception:
            pass
    
    # Read credentials
    credentials = read_credentials()
    if not credentials:
        sys.exit(0)  # Silent exit if no credentials
    
    # Fetch usage
    rate_limits = fetch_usage(credentials)
    if not rate_limits:
        sys.exit(0)  # Silent exit on API error
    
    # Write cache
    if write_cache(rate_limits):
        print(f"[OAL] Rate limits updated: daily={rate_limits.get('fiveHourPercent', 'N/A')}%, weekly={rate_limits.get('weeklyPercent', 'N/A')}%")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
