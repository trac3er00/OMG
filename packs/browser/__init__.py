"""Browser/Playwright pack — lazy-loaded on first use."""

try:
    from runtime.playwright_pack import *  # noqa: F401, F403
except ImportError:
    pass
