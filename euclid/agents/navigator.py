from __future__ import annotations

import os

import litellm
from rich.console import Console
from rich.table import Table

from euclid.core.knowledge_graph import Concept, KnowledgeGraph
from euclid.core.student_state import ConceptState, StateManager


console = Console()

SYSTEM_PROMPT = """You are the Navigator — one of four agents inside Euclid, an open source math tutor.

Your job: given a student's current knowledge state, explain what they should learn next and why.

Rules:
- Be direct. One paragraph maximum.
- Name the concept, explain in one sentence why it is the right next step.
- Name one real-world situation where this concept is used.
- Never use the word "journey". Never say "let's explore". Never say "great job".
- Do not repeat information already visible in the progress table."""


def _model() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude-3-5-haiku-20241022"
    if os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    return "ollama/qwen2.5:7b"


def _ask_llm(messages: list[dict]) -> str:
    response = litellm.completion(
        model=_model(),
        messages=messages,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


class Navigator:
    def __init__(self, graph: KnowledgeGraph, state: StateManager) -> None:
        self.graph = graph
        self.state = state

    def show_progress(self) -> None:
        mastered   = self.state.get_mastered()
        all_states = self.state.get_all_states()
        progress   = self.graph.progress(mastered)

        console.print(
            f"\n[bold]Progress[/bold] — "
            f"{progress['mastered']}/{progress['total']} concepts mastered "
            f"({progress['percent']}%)\n"
        )

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Domain")
        table.add_column("Mastered", justify="right")
        table.add_column("Total",    justify="right")
        table.add_column("Bar",      no_wrap=True)

        for domain, stats in sorted(progress["by_domain"].items()):
            done  = stats["mastered"]
            total = stats["total"]
            pct   = done / total if total else 0
            bar   = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
            table.add_row(domain, str(done), str(total), f"[cyan]{bar}[/cyan]")

        console.print(table)

    def show_frontier(self) -> list[Concept]:
        mastered  = self.state.get_mastered()
        frontier  = self.graph.frontier(mastered)

        if not frontier:
            console.print("\n[bold green]All concepts mastered.[/bold green]")
            return []

        console.print(f"\n[bold]Ready to learn[/bold] — {len(frontier)} concepts unlocked:\n")

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Concept")
        table.add_column("Domain")
        table.add_column("Grade", justify="right")
        table.add_column("Unlocks", justify="right")

        for concept in sorted(frontier, key=lambda c: c.grade):
            unlocks = len(self.graph.dependents(concept.id))
            table.add_row(
                concept.name,
                concept.domain,
                str(concept.grade),
                str(unlocks),
            )

        console.print(table)
        return frontier

    def suggest(self) -> Concept | None:
        mastered = self.state.get_mastered()
        next_concept = self.graph.suggest_next(mastered, self.state)

        if not next_concept:
            console.print("\n[bold green]All concepts mastered.[/bold green]")
            return None

        prereqs = [
            self.graph.get(p).name
            for p in next_concept.prerequisites
        ]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Student's next concept: {next_concept.name}\n"
                    f"Description: {next_concept.description}\n"
                    f"Grade level: {next_concept.grade}\n"
                    f"Prerequisites they have mastered: {', '.join(prereqs) if prereqs else 'none (entry concept)'}\n\n"
                    f"Explain why this is the right next step and give one real-world use."
                ),
            },
        ]

        explanation = _ask_llm(messages)
        console.print(f"\n[bold cyan]Next:[/bold cyan] {next_concept.name}\n")
        console.print(explanation)
        console.print()

        return next_concept

    def path_to(self, concept_name: str) -> None:
        target = next(
            (c for c in self.graph if concept_name.lower() in c.name.lower()),
            None,
        )

        if not target:
            console.print(f"[red]Concept not found:[/red] {concept_name}")
            return

        mastered = self.state.get_mastered()
        path     = self.graph.path_to(target.id, mastered)

        if not path:
            console.print(f"[bold green]Already mastered:[/bold green] {target.name}")
            return

        console.print(f"\n[bold]Path to[/bold] {target.name} — {len(path)} steps:\n")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Step", justify="right", style="dim")
        table.add_column("Concept")
        table.add_column("Domain")
        table.add_column("Grade", justify="right")

        for i, concept in enumerate(path, 1):
            state = self.state.get_concept_state(concept.id)
            style = (
                "green" if state == ConceptState.MASTERED else
                "yellow" if state == ConceptState.LEARNING else
                ""
            )
            table.add_row(
                str(i),
                f"[{style}]{concept.name}[/{style}]" if style else concept.name,
                concept.domain,
                str(concept.grade),
            )

        console.print(table)
