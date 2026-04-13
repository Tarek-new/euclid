from __future__ import annotations

import os

import litellm
from rich.console import Console

from euclid.agents.assessor import Assessor
from euclid.agents.navigator import Navigator
from euclid.agents.socrates import Socrates
from euclid.agents.verifier import Verifier
from euclid.core.knowledge_graph import KnowledgeGraph
from euclid.core.student_state import ConceptState, StateManager


console = Console()


def _model() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude-3-5-haiku-20241022"
    if os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    return "ollama/qwen2.5:7b"


def _resolve_concept(graph: KnowledgeGraph, query: str):
    """
    Given a free-text query from the user, find the closest concept in the graph.
    Uses LLM to match natural language to a concept_id.
    """
    concept_list = "\n".join(
        f"{c.id}: {c.name} (grade {c.grade})"
        for c in sorted(graph, key=lambda c: c.grade)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a concept resolver. Given a student's free-text query, "
                "return the single most relevant concept_id from the list below. "
                "Return only the concept_id. Nothing else."
                f"\n\nConcepts:\n{concept_list}"
            ),
        },
        {"role": "user", "content": query},
    ]
    response = litellm.completion(
        model=_model(),
        messages=messages,
        temperature=0.0,
    )
    concept_id = response.choices[0].message.content.strip().lower()
    return graph.concepts.get(concept_id)


class Orchestrator:
    def __init__(self, student_name: str = "default") -> None:
        self.graph     = KnowledgeGraph()
        self.state     = StateManager(student_name)
        self.assessor  = Assessor(self.graph, self.state)
        self.navigator = Navigator(self.graph, self.state)
        self.socrates  = Socrates(self.graph, self.state)
        self.verifier  = Verifier(self.graph, self.state)

    def run_assess(self, query: str | None = None) -> None:
        """
        euclid assess [topic]
        Maps what the student knows. Runs placement if no topic given.
        """
        if not query:
            self.assessor.run_placement()
            return

        concept = _resolve_concept(self.graph, query)
        if not concept:
            console.print(f"[red]Could not find concept:[/red] {query}")
            return

        self.assessor.assess(concept)

    def run_practice(self, query: str | None = None) -> None:
        """
        euclid practice [topic]
        Socratic dialogue on a concept. If no topic given, picks next suggested.
        """
        mastered = self.state.get_mastered()

        if query:
            concept = _resolve_concept(self.graph, query)
        else:
            concept = self.graph.suggest_next(mastered, self.state)

        if not concept:
            console.print("[dim]Nothing to practice. Run[/dim] [bold]euclid assess[/bold] [dim]first.[/dim]")
            return

        if not self.graph.prerequisites_met(concept.id, mastered):
            broken = self.graph.broken_prerequisites(concept.id, mastered)
            names  = ", ".join(c.name for c in broken)
            console.print(f"[yellow]Prerequisites not met:[/yellow] {names}")
            return

        from euclid.agents.assessor import _generate_problem
        problem = _generate_problem(concept)

        resolved = self.socrates.practice(concept, problem)

        if resolved:
            self.verifier.verify(concept, problem)

    def run_explain(self, query: str) -> None:
        """
        euclid explain <topic>
        Direct explanation from first principles. No Socratic dialogue.
        """
        concept = _resolve_concept(self.graph, query)
        if not concept:
            console.print(f"[red]Could not find concept:[/red] {query}")
            return
        self.socrates.explain(concept)

    def run_progress(self) -> None:
        """
        euclid progress
        Show mastery progress and domain breakdown.
        """
        self.navigator.show_progress()
        self.navigator.show_frontier()

    def run_path(self, query: str) -> None:
        """
        euclid path <topic>
        Show the ordered sequence of concepts to reach a target.
        """
        self.navigator.path_to(query)

    def run_audit(self, domain: str | None = None) -> None:
        """
        euclid audit [domain]
        Transfer-test all mastered concepts to confirm real understanding.
        """
        self.verifier.audit(domain)

    def run_next(self) -> None:
        """
        euclid next
        Show what the student should learn next and why.
        """
        self.navigator.suggest()

    def close(self, summary: str = "") -> None:
        self.state.end_session(summary)
