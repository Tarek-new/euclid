from __future__ import annotations

import json
import os

import litellm
from rich.console import Console
from rich.markdown import Markdown

from euclid.core.knowledge_graph import Concept, KnowledgeGraph
from euclid.core.student_state import ConceptState, StateManager


console = Console()

SYSTEM_PROMPT = """You are the Verifier — one of four agents inside Euclid, an open source math tutor.

Your job: confirm that a student's mastery of a concept is real and not surface-level pattern matching.

A student who has just "mastered" a concept may have only memorised the surface pattern of the problem
they were shown. Your job is to catch this by testing transfer — asking a structurally identical problem
with completely different surface features.

Rules:
- Generate a transfer problem: same underlying concept, completely different numbers, context, and framing.
- If the first problem was abstract (pure numbers), make yours applied (real-world context).
- If the first problem was applied, make yours abstract.
- After receiving the student's answer, return a JSON object with this exact structure:
  {
    "transfer_confirmed": true | false,
    "verdict":            "mastered" | "revert_to_learning",
    "reasoning":          "one sentence explaining the verdict"
  }

transfer_confirmed is true only if the student solved the transfer problem correctly AND
used reasoning that shows they understand the concept, not just the surface pattern.

If transfer_confirmed is false, verdict must be "revert_to_learning".
You only return valid JSON. No extra text outside the JSON block."""


def _model() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude-3-5-haiku-20241022"
    if os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    return "ollama/qwen2.5:7b"


def _ask_llm(messages: list[dict], temperature: float = 0.3) -> str:
    response = litellm.completion(
        model=_model(),
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def _generate_transfer_problem(concept: Concept, original_problem: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Concept: {concept.name}\n"
                f"Description: {concept.description}\n"
                f"Original problem the student just solved: {original_problem}\n\n"
                f"Generate one transfer problem. Return only the problem. No preamble."
            ),
        },
    ]
    return _ask_llm(messages, temperature=0.6)


def _evaluate_transfer(
    concept: Concept,
    original_problem: str,
    transfer_problem: str,
    student_answer: str,
) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Concept: {concept.name}\n"
                f"Original problem: {original_problem}\n"
                f"Transfer problem: {transfer_problem}\n"
                f"Student answer: {student_answer}\n\n"
                f"Evaluate and return the JSON verdict."
            ),
        },
    ]
    raw = _ask_llm(messages, temperature=0.1)

    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "transfer_confirmed": False,
            "verdict":            "revert_to_learning",
            "reasoning":          "Could not parse response.",
        }


class Verifier:
    def __init__(self, graph: KnowledgeGraph, state: StateManager) -> None:
        self.graph = graph
        self.state = state

    def verify(self, concept: Concept, original_problem: str) -> bool:
        """
        Run a transfer verification on a concept the student just marked mastered.
        Returns True if mastery is confirmed, False if reverted to learning.
        """
        console.print(
            f"\n[bold cyan]Verifying:[/bold cyan] {concept.name} — "
            f"[dim]transfer check[/dim]\n"
        )

        transfer_problem = _generate_transfer_problem(concept, original_problem)
        console.print(Markdown(transfer_problem))
        console.print()

        from rich.prompt import Prompt
        student_answer = Prompt.ask("[bold yellow]Your answer[/bold yellow]")

        result = _evaluate_transfer(
            concept, original_problem, transfer_problem, student_answer
        )

        if result["transfer_confirmed"]:
            console.print(
                f"\n[bold green]Verified:[/bold green] {concept.name} — "
                f"[dim]{result['reasoning']}[/dim]\n"
            )
            return True

        self.state.set_concept_state(concept.id, ConceptState.LEARNING)
        console.print(
            f"\n[bold yellow]Revert to learning:[/bold yellow] {concept.name} — "
            f"[dim]{result['reasoning']}[/dim]\n"
        )

        broken = self.graph.broken_prerequisites(concept.id, self.state.get_mastered())
        if broken:
            names = ", ".join(c.name for c in broken)
            console.print(f"[dim]Revisit first → {names}[/dim]\n")

        return False

    def audit(self, domain: str | None = None) -> None:
        """
        Audit all concepts the student has marked mastered.
        Reverts any that fail the transfer check.
        Used to catch pattern-matching mastery built up over time.
        """
        mastered = list(self.state.get_mastered())

        if domain:
            mastered = [
                cid for cid in mastered
                if self.graph.get(cid).domain == domain
            ]

        if not mastered:
            console.print("[dim]No mastered concepts to audit.[/dim]")
            return

        console.print(
            f"\n[bold]Audit[/bold] — verifying {len(mastered)} mastered concepts\n"
        )

        reverted = 0
        for concept_id in mastered:
            concept = self.graph.get(concept_id)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Generate one diagnostic problem for: {concept.name}\n"
                        f"Description: {concept.description}\n"
                        f"Return only the problem."
                    ),
                },
            ]
            problem = _ask_llm(messages, temperature=0.6)
            confirmed = self.verify(concept, problem)

            if not confirmed:
                reverted += 1

        console.print(
            f"\n[bold]Audit complete[/bold] — "
            f"{len(mastered) - reverted}/{len(mastered)} confirmed, "
            f"{reverted} reverted to learning.\n"
        )
