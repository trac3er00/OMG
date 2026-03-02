"""Runtime adapters for OAL v1."""

from .claude import ClaudeAdapter
from .gpt import GPTAdapter
from .local import LocalAdapter


def get_adapters():
    return {
        "claude": ClaudeAdapter(),
        "gpt": GPTAdapter(),
        "local": LocalAdapter(),
    }
