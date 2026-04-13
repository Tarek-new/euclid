from __future__ import annotations

import json
import os

import litellm
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from euclid.core.knowledge_graph import Concept, KnowledgeGraph
from euclid.core.student_state import ConceptState, StateManager


console = Console()

SYSTEM_PROMPT = """You are the Assessor — one of four agents inside Euclid, an open source math tutor.

Your job: determine whether a student has genuinely mastered a specific math concept.

Rules:
- Ask exactly ONE diagnostic problem per concept. Not a definition. A real problem that requires applying the concept.
- The problem must be solvable in under two minutes.
- After the student responds, analyse their answer. Do not reveal whether they are right or wrong yet.
- Return a JSON object with this exact structure:
  {
    "verdict":     "mastered" | "learning" | "unknown",
    "correct":     true | false,
    "gap":         "one sentence describing the specific gap if incorrect, empty string if correct",
    "broken_prereq": "concept_id of the most likely broken prerequisite, or empty string"
  }

Verdict rules:
- "mastered"  — answer is correct and the student shows understanding of why, not just the result
- "learning"  — answer is partially correct or correct but with clear mechanical error
- "unknown"   — answer is incorrect and reveals a fundamental gap

You only return valid JSON. No extra text outside the JSON block."""


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
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def _generate_problem(concept: Concept) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Generate a single diagnostic problem for this concept:\n\n"
                f"Concept: {concept.name}\n"
                f"Description: {concept.description}\n"
                f"Grade level: {concept.grade}\n\n"
                f"Return only the problem statement. No preamble. No answer."
            ),
        },
    ]
    return _ask_llm(messages)


def _evaluate_response(concept: Concept, problem: str, student_answer: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Concept being assessed: {concept.name}\n"
                f"Description: {concept.description}\n\n"
                f"Problem asked: {problem}\n\n"
                f"Student answer: {student_answer}\n\n"
                f"Evaluate the answer and return the JSON verdict."
            ),
        },
    ]
    raw = _ask_llm(messages)

    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "verdict":       "unknown",
            "correct":       False,
            "gap":           "Could not parse student response.",
            "broken_prereq": "",
        }


class Assessor:
    def __init__(self, graph: KnowledgeGraph, state: StateManager) -> None:
        self.graph = graph
        self.state = state

    def assess(self, concept: Concept) -> dict:
        self.state.set_concept_state(concept.id, ConceptState.SEEN)

        console.print(f"\n[bold cyan]Assessing:[/bold cyan] {concept.name}\n")

        problem = _generate_problem(concept)
        console.print(Markdown(problem))
        console.print()

        student_answer = Prompt.ask("[bold yellow]Your answer[/bold yellow]")

        result = _evaluate_response(concept, problem, student_answer)

        self.state.record_attempt(concept.id, correct=result["correct"])

        if result["verdict"] == "mastered":
            self.state.set_concept_state(concept.id, ConceptState.MASTERED)
            unlocked = self.graph.dependents(concept.id)
            console.print(f"\n[bold green]Mastered:[/bold green] {concept.name}")
            if unlocked:
                names = ", ".join(c.name for c in unlocked[:3])
                console.print(f"[dim]Unlocks → {names}[/dim]")

        elif result["verdict"] == "learning":
            self.state.set_concept_state(concept.id, ConceptState.LEARNING)
            console.print(f"\n[bold yellow]In progress:[/bold yellow] {concept.name}")
            if result["gap"]:
                console.print(f"[dim]{result['gap']}[/dim]")

        else:
            self.state.set_concept_state(concept.id, ConceptState.UNKNOWN)
            console.print(f"\n[bold red]Gap found:[/bold red] {concept.name}")
            if result["gap"]:
                console.print(f"[dim]{result['gap']}[/dim]")

            if result.get("broken_prereq") and result["broken_prereq"] in self.graph.concepts:
                prereq = self.graph.get(result["broken_prereq"])
                console.print(
                    f"[dim]Root cause → missing prerequisite: [bold]{prereq.name}[/bold][/dim]"
                )

        return result

    def run_placement(self, domain: str | None = None) -> None:
        """
        Full placement assessment. Tests a sample of concepts across
        the graph to rapidly build an initial knowledge state.
        Stops early if three consecutive unknowns are detected.
        """
        mastered = self.state.get_mastered()
        candidates = (
            self.graph.by_domain(domain) if domain
            else list(self.graph.concepts.values())
        )
        candidates = [
            c for c in sorted(candidates, key=lambda c: c.grade)
            if self.state.get_concept_state(c.id) == ConceptState.UNKNOWN
        ]

        step        = max(1, len(candidates) // 8)
        sampled     = candidates[::step][:8]
        consecutive = 0

        console.print(
            "\n[bold]Placement assessment[/bold] — "
            f"testing {len(sampled)} concepts to find your level.\n"
        )

        for concept in sampled:
            if not self.graph.prerequisites_met(concept.id, mastered):
                continue

            result = self.assess(concept)

            if result["verdict"] == "mastered":
                mastered.add(concept.id)
                consecutive = 0
            else:
                consecutive += 1

            if consecutive >= 3:
                console.print(
                    "\n[dim]Found your level. Stopping placement.[/dim]"
                )
                break
