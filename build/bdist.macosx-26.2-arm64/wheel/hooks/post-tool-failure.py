#!/usr/bin/env python3
"""PostToolUseFailure Hook — Logs tool failures for enhanced tracking."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from _common import setup_crash_handler, json_input, get_feature_flag, log_hook_error

setup_crash_handler('post-tool-failure')

data = json_input()
tool_name = data.get('tool_name', 'unknown')
error = data.get('error', data.get('message', 'unknown error'))

# Log to hook-errors.jsonl using the shared utility
log_hook_error('post-tool-failure', error, context={'tool': tool_name})

sys.exit(0)
