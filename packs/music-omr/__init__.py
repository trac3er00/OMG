"""Music OMR pack — lazy-loaded on first use."""

try:
    from runtime.music_omr_testbed import *  # noqa: F401, F403
except ImportError:
    pass
