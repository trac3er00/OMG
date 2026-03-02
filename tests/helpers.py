import subprocess
import json
import os
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent / 'hooks'
PROJECT_ROOT = Path(__file__).parent.parent


def run_hook(hook_name, input_data, env=None, cwd=None):
    """Run a hook via subprocess, return (stdout_str, stderr_str, exit_code).
    stdout_str is parsed as JSON if possible, else raw string."""
    hook_path = HOOKS_DIR / f'{hook_name}.py'
    run_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        ['python3', str(hook_path)],
        input=json.dumps(input_data).encode(),
        capture_output=True,
        cwd=str(cwd or PROJECT_ROOT),
        env=run_env
    )
    try:
        stdout = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        stdout = result.stdout.decode()
    return stdout, result.stderr.decode(), result.returncode


def make_ledger_entry(tool, command=None, exit_code=0, file=None, success=True):
    """Create a tool-ledger.jsonl entry dict for testing."""
    entry = {'tool': tool, 'exit_code': exit_code, 'success': success}
    if command:
        entry['command'] = command
    if file:
        entry['file'] = file
    return entry


def setup_state(tmp_dir, files_dict):
    """Create state files from a dict of {relative_path: content}."""
    for rel_path, content in files_dict.items():
        full_path = Path(tmp_dir) / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            full_path.write_text(json.dumps(content))
        else:
            full_path.write_text(str(content))


def assert_injection_contains(output, *keywords):
    """Assert contextInjection (or string output) contains all keywords."""
    if isinstance(output, dict):
        text = output.get('contextInjection', '')
    else:
        text = str(output)
    for kw in keywords:
        assert kw in text, f"Expected '{kw}' in injection but got: {text[:200]}"


def assert_injection_under_budget(output, max_chars):
    """Assert contextInjection length is within budget."""
    if isinstance(output, dict):
        text = output.get('contextInjection', '')
    else:
        text = str(output)
    assert len(text) <= max_chars, f"Budget exceeded: {len(text)} > {max_chars} chars"
