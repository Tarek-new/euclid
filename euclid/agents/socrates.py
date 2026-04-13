from __future__ import annotations

import os

import litellm
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from euclid.core.knowledge_graph import Concept, KnowledgeGraph
from euclid.core.student_state import ConceptState, StateManager


console = Console()

SYSTEM_PROMPT = """You are Socrates — one of four agents inside Euclid, an open source math tutor.

Your only tool is questions. You never give answers. You never confirm an answer is correct directly.
You ask questions that force the student to think one step deeper until they arrive at the answer themselves.

Rules:
- Never say "correct", "exactly", "great", "well done", or any praise.
- Never give the answer even if the student is completely stuck. Instead, break the question into a smaller step.
- Ask one question per response. Never two.
- Keep questions short. One or two sentences maximum.
- If the student is stuck after 3 attempts, ask a simpler version of the same question — do not explain.
- If the student arrives at the correct answer, respond with exactly: RESOLVED
- If after 6 exchanges the student has not arrived at the answer, respond with exactly: ESCALATE

You are not a teacher. You are a mirror. The student must find the answer in themselves."""


EXPLANATION_PROMPT = """You are the Explanation module inside Euclid, an open source math tutor.

A student has been unable to solve a problem after multiple attempts via Socratic dialogue.
You now explain the concept from first principles — but only using what the student already knows.

Rules:
- Start from the student's last correct statement in the conversation.
- Build the explanation in at most 3 steps.
- End with the same problem restated so the student can now solve it themselves.
- No praise. No encouragement. Just the clearest possible explanation."""


def _model() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude-3-5-haiku-20241022"
    if os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    return "ollama/qwen2.5:7b"


def _ask_llm(messages: list[dict], temperature: float = 0.4) -> str:
    response = litellm.completion(
        model=_model(),
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


class Socrates:
    def __init__(self, graph: KnowledgeGraph, state: StateManager) -> None:
        self.graph = graph
        self.state = state

    def _build_context(self, concept: Concept, problem: str) -> str:
        mastered   = self.state.get_mastered()
        prereq_names = [
            self.graph.get(p).name
            for p in concept.prerequisites
            if p in mastered
        ]
        return (
            f"Concept being taught: {concept.name}\n"
            f"Description: {concept.description}\n"
            f"Prerequisites the student has mastered: "
            f"{', '.join(prereq_names) if prereq_names else 'none'}\n"
            f"Problem: {problem}"
        )

    def _escalate(
        self,
        concept: Concept,
        problem: str,
        history: list[dict],
    ) -> None:
        context = self._build_context(concept, problem)
        messages = [
            {"role": "system", "content": EXPLANATION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{context}\n\n"
                    f"Conversation so far:\n"
                    + "\n".join(
                        f"{m['role'].upper()}: {m['content']}"
                        for m in history
                        if m["role"] != "system"
                    )
                ),
            },
        ]
        explanation = _ask_llm(messages, temperature=0.2)
        console.print("\n")
        console.print(Markdown(explanation))
        console.print()

        self.state.set_concept_state(concept.id, ConceptState.LEARNING)

    def practice(self, concept: Concept, problem: str) -> bool:
        """
        Run a Socratic dialogue session on a given problem.
        Returns True if the student resolved it, False if escalated.
        """
        context  = self._build_context(concept, problem)
        history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{context}\n\n"
                    f"Begin the Socratic dialogue. Ask your first question."
                ),
            },
        ]

        console.print(f"\n[bold cyan]Practice:[/bold cyan] {concept.name}\n")
        console.print(Markdown(f"**Problem:** {problem}\n"))

        exchanges = 0

        while exchanges < 6:
            response = _ask_llm(history)

            if response.strip() == "RESOLVED":
                self.state.set_concept_state(concept.id, ConceptState.MASTERED)
                self.state.record_attempt(concept.id, correct=True)
                console.print("\n[bold green]Solved.[/bold green]\n")
                unlocked = self.graph.dependents(concept.id)
                if unlocked:
                    names = ", ".join(c.name for c in unlocked[:3])
                    console.print(f"[dim]Unlocks → {names}[/dim]\n")
                return True

            if response.strip() == "ESCALATE":
                self.state.record_attempt(concept.id, correct=False)
                self._escalate(concept, problem, history)
                return False

            history.append({"role": "assistant", "content": response})
            console.print(Markdown(response))

            student_input = Prompt.ask("\n[bold yellow]→[/bold yellow]")
            history.append({"role": "user", "content": student_input})

            exchanges += 1

        self.state.record_attempt(concept.id, correct=False)
        self._escalate(concept, problem, history)
        return False

    def explain(self, concept: Concept) -> None:
        """
        Direct explain mode — student asked for an explanation explicitly.
        Builds from prerequisites upward, ends with a problem to solve.
        """
        mastered     = self.state.get_mastered()
        prereq_names = [
            self.graph.get(p).name
            for p in concept.prerequisites
            if p in mastered
        ]

        messages = [
            {"role": "system", "content": EXPLANATION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Concept: {concept.name}\n"
                    f"Description: {concept.description}\n"
                    f"Prerequisites the student has mastered: "
                    f"{', '.join(prereq_names) if prereq_names else 'none'}\n\n"
                    f"Explain from first principles and end with a problem."
                ),
            },
        ]

        explanation = _ask_llm(messages, temperature=0.2)
        console.print(f"\n[bold cyan]Explanation:[/bold cyan] {concept.name}\n")
        console.print(Markdown(explanation))
        console.print()
