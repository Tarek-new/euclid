from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from euclid.core.student_state import ConceptState, StateManager


GRAPH_PATH = Path(__file__).parent.parent / "data" / "math_graph.json"


class Concept:
    def __init__(self, id: str, data: dict) -> None:
        self.id           = id
        self.name         = data["name"]
        self.domain       = data["domain"]
        self.grade        = data["grade"]
        self.prerequisites = data["prerequisites"]
        self.description  = data["description"]

    def __repr__(self) -> str:
        return f"Concept({self.id!r}, grade={self.grade})"


class KnowledgeGraph:
    def __init__(self) -> None:
        raw = json.loads(GRAPH_PATH.read_text())
        self.concepts: dict[str, Concept] = {
            id: Concept(id, data) for id, data in raw.items()
        }

    def get(self, concept_id: str) -> Concept:
        return self.concepts[concept_id]

    def prerequisites_met(self, concept_id: str, mastered: set[str]) -> bool:
        return all(p in mastered for p in self.concepts[concept_id].prerequisites)

    def frontier(self, mastered: set[str]) -> list[Concept]:
        """
        Concepts the student has not mastered but whose prerequisites are all met.
        These are the concepts they are ready to learn right now.
        """
        return [
            c for c in self.concepts.values()
            if c.id not in mastered and self.prerequisites_met(c.id, mastered)
        ]

    def broken_prerequisites(self, concept_id: str, mastered: set[str]) -> list[Concept]:
        """
        Given a concept a student is struggling with, return the prerequisites
        they have not yet mastered. These are the actual gaps causing the failure.
        """
        return [
            self.concepts[p]
            for p in self.concepts[concept_id].prerequisites
            if p not in mastered
        ]

    def path_to(self, concept_id: str, mastered: set[str]) -> list[Concept]:
        """
        Shortest ordered sequence of unmastered concepts the student must learn
        to reach a target concept. Uses topological ordering of the prerequisite graph.
        """
        needed: list[str] = []
        visited: set[str] = set()

        def walk(cid: str) -> None:
            if cid in visited:
                return
            visited.add(cid)
            for prereq in self.concepts[cid].prerequisites:
                walk(prereq)
            if cid not in mastered:
                needed.append(cid)

        walk(concept_id)
        return [self.concepts[cid] for cid in needed]

    def by_domain(self, domain: str) -> list[Concept]:
        return [c for c in self.concepts.values() if c.domain == domain]

    def by_grade(self, grade: int) -> list[Concept]:
        return [c for c in self.concepts.values() if c.grade == grade]

    def dependents(self, concept_id: str) -> list[Concept]:
        """
        All concepts that directly depend on this concept as a prerequisite.
        Used to show the student what mastering this concept unlocks.
        """
        return [
            c for c in self.concepts.values()
            if concept_id in c.prerequisites
        ]

    def progress(self, mastered: set[str]) -> dict:
        total    = len(self.concepts)
        done     = len(mastered)
        frontier = self.frontier(mastered)

        by_domain: dict[str, dict] = {}
        for c in self.concepts.values():
            d = by_domain.setdefault(c.domain, {"total": 0, "mastered": 0})
            d["total"] += 1
            if c.id in mastered:
                d["mastered"] += 1

        return {
            "total":          total,
            "mastered":       done,
            "percent":        round(done / total * 100, 1),
            "ready_to_learn": len(frontier),
            "by_domain":      by_domain,
        }

    def infer_prerequisites(self, concept_id: str, state_manager: StateManager) -> set[str]:
        """
        Backward inference — if a student masters concept X, they implicitly
        know all prerequisites of X (recursively). Mark them as mastered.
        Returns the set of newly inferred concept IDs.
        """
        inferred: set[str] = set()

        def walk(cid: str) -> None:
            for prereq_id in self.concepts[cid].prerequisites:
                if state_manager.get_concept_state(prereq_id) != ConceptState.MASTERED:
                    state_manager.set_concept_state(prereq_id, ConceptState.MASTERED)
                    inferred.add(prereq_id)
                walk(prereq_id)

        walk(concept_id)
        return inferred

    def suggest_next(self, mastered: set[str], state_manager: StateManager) -> Concept | None:
        """
        From the frontier, pick the concept with the lowest grade level
        the student has already seen or attempted. Prioritises continuity
        over jumping to something new.
        """
        all_states = state_manager.get_all_states()
        candidates = self.frontier(mastered)

        if not candidates:
            return None

        in_progress = [
            c for c in candidates
            if all_states.get(c.id) in (ConceptState.SEEN, ConceptState.LEARNING)
        ]

        if in_progress:
            return min(in_progress, key=lambda c: c.grade)

        return min(candidates, key=lambda c: c.grade)

    def __iter__(self) -> Iterator[Concept]:
        return iter(self.concepts.values())

    def __len__(self) -> int:
        return len(self.concepts)
