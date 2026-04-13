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
- CRITICAL: calibrate the problem to the student's age and background provided below.
  A 25-year-old professional being asked "how many apples are there?" is insulting.
  For adults assessing basic concepts, use real-world adult contexts: finances, measurements, data, engineering.
  For children, use age-appropriate contexts.
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


def _get_student_profile() -> str:
    console.print("\n[bold]Before we start — two quick questions.[/bold]\n")
    age = Prompt.ask("[bold yellow]Your age[/bold yellow]")
    background = Prompt.ask(
        "[bold yellow]Your background[/bold yellow] "
        "[dim](e.g. student, engineer, teacher, self-learning)[/dim]"
    )
    console.print()
    return f"Age: {age}. Background: {background}."


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


def _generate_problem(concept: Concept, profile: str = "") -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Generate a single diagnostic problem for this concept:\n\n"
                f"Concept: {concept.name}\n"
                f"Description: {concept.description}\n"
                f"Grade level: {concept.grade}\n"
                f"Student profile: {profile if profile else 'unknown'}\n\n"
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

    def assess(self, concept: Concept, profile: str = "") -> dict:
        self.state.set_concept_state(concept.id, ConceptState.SEEN)

        console.print(f"\n[bold cyan]Assessing:[/bold cyan] {concept.name}\n")

        problem = _generate_problem(concept, profile)
        console.print(Markdown(problem))
        console.print()

        student_answer = Prompt.ask("[bold yellow]Your answer[/bold yellow]")

        result = _evaluate_response(concept, problem, student_answer)

        self.state.record_attempt(concept.id, correct=result["correct"])

        if result["verdict"] == "mastered":
            self.state.set_concept_state(concept.id, ConceptState.MASTERED)
            inferred = self.graph.infer_prerequisites(concept.id, self.state)
            unlocked = self.graph.dependents(concept.id)
            console.print(f"\n[bold green]Mastered:[/bold green] {concept.name}")
            if inferred:
                names = ", ".join(self.graph.get(cid).name for cid in list(inferred)[:3])
                console.print(f"[dim]Inferred → {names}[/dim]")
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

        Placement does NOT require prerequisites to be met — the point
        is discovery, not readiness. We sample evenly across grade levels
        to binary-search the student's actual level.

        Stops early if three consecutive unknowns are detected.
        """
        mastered = self.state.get_mastered()

        all_concepts = (
            self.graph.by_domain(domain) if domain
            else list(self.graph.concepts.values())
        )

        candidates = sorted(
            [c for c in all_concepts
             if self.state.get_concept_state(c.id) == ConceptState.UNKNOWN],
            key=lambda c: c.grade,
        )

        if not candidates:
            console.print("[dim]All concepts already assessed.[/dim]")
            return

        # Sample evenly across grade levels — one concept per grade band
        grades     = sorted({c.grade for c in candidates})
        sampled    = []
        per_grade  = {g: [c for c in candidates if c.grade == g] for g in grades}

        for grade in grades:
            group = per_grade[grade]
            # pick the concept with fewest prerequisites for cleanest assessment
            sampled.append(min(group, key=lambda c: len(c.prerequisites)))
            if len(sampled) >= 8:
                break

        consecutive = 0

        profile = _get_student_profile()

        console.print(
            "\n[bold]Placement assessment[/bold] — "
            f"testing {len(sampled)} concepts across grades "
            f"{sampled[0].grade}–{sampled[-1].grade}.\n"
        )

        for concept in sampled:
            result = self.assess(concept, profile)

            if result["verdict"] == "mastered":
                mastered.add(concept.id)
                consecutive = 0
            else:
                consecutive += 1

            if consecutive >= 3:
                console.print("\n[dim]Found your level. Stopping placement.[/dim]")
                break

        console.print(
            f"\n[dim]Placement complete. "
            f"Run [bold]euclid progress[/bold] to see your knowledge map.[/dim]\n"
        )
