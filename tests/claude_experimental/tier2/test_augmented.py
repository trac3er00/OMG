"""Tests for MemoryAugmenter — prompt augmentation with memory context."""
from __future__ import annotations

import pytest

from claude_experimental.memory.augmented_generation import MemoryAugmenter
from claude_experimental.memory.semantic import SemanticMemory
from claude_experimental.memory.store import MemoryStore

pytestmark = pytest.mark.experimental


class TestMemoryAugmenter:
    def test_augment_prompt_injects_context(self):
        """augment_prompt injects relevant memory context into the prompt."""
        # Store memories at the project-scoped default path (CLAUDE_PROJECT_DIR)
        store = MemoryStore(scope="project")
        sem = SemanticMemory(store)
        # Two facts with different lengths so BM25 normalization produces varied scores
        sem.store_fact("Python memory management", importance=1.0, scope="project")
        sem.store_fact(
            "Python is a versatile programming language for web development"
            " and data science and automation and scripting",
            importance=0.8,
            scope="project",
        )

        augmenter = MemoryAugmenter()
        result = augmenter.augment_prompt("Python", context_scope="project")

        assert "Relevant Context from Memory" in result
        assert "Python" in result

    def test_augment_prompt_max_memories_zero(self):
        """max_memories=0 returns base prompt unchanged."""
        augmenter = MemoryAugmenter()
        base = "Tell me about testing"
        result = augmenter.augment_prompt(base, max_memories=0)
        assert result == base

    def test_augment_prompt_no_memories(self):
        """Empty memory DB returns base prompt unchanged."""
        augmenter = MemoryAugmenter()
        base = "Explain containerization"
        result = augmenter.augment_prompt(base, context_scope="project")
        assert result == base
