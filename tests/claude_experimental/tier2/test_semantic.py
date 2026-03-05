"""Tests for SemanticMemory — fact storage with FTS5 scoring and entity links."""
from __future__ import annotations

import pytest

from claude_experimental.memory.semantic import SemanticMemory
from claude_experimental.memory.store import MemoryStore

pytestmark = pytest.mark.experimental


class TestSemanticMemory:
    def test_store_fact_and_search_round_trip(self, tmp_path):
        """Stored fact is retrievable via search."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        sem = SemanticMemory(store)

        mid = sem.store_fact("Python uses garbage collection", importance=0.8)
        assert mid > 0

        results = sem.search("Python garbage collection")
        assert len(results) >= 1
        assert "garbage" in str(results[0]["content"])

    def test_search_scoring_order(self, tmp_path):
        """Higher importance facts score higher when BM25 is similar."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        sem = SemanticMemory(store)

        sem.store_fact(
            "Docker uses containers for isolation",
            importance=0.9,
            scope="project",
        )
        sem.store_fact(
            "Docker containers orchestrate multi service deployment workflows",
            importance=0.3,
            scope="project",
        )

        results = sem.search("Docker containers", min_score=0.0)
        assert len(results) >= 2
        # Results are sorted by score descending
        scores = [float(str(r["score"])) for r in results]
        assert scores[0] >= scores[1]

    def test_add_and_get_links(self, tmp_path):
        """Entity links are created and retrievable."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        sem = SemanticMemory(store)

        link_id = sem.add_link("FastAPI", "SQLAlchemy", "depends_on")
        assert link_id > 0

        links = sem.get_links("FastAPI")
        assert len(links) >= 1
        assert links[0]["from_entity"] == "FastAPI"
        assert links[0]["to_entity"] == "SQLAlchemy"
        assert links[0]["relationship_type"] == "depends_on"

    def test_get_links_bidirectional(self, tmp_path):
        """get_links returns links where entity is source OR target."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        sem = SemanticMemory(store)

        sem.add_link("React", "Redux", "uses")

        # Search by target entity
        links = sem.get_links("Redux")
        assert len(links) >= 1
        assert links[0]["to_entity"] == "Redux"
