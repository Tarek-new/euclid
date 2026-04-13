from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from euclid import __version__


app     = Console()
cli     = typer.Typer(
    name="euclid",
    help="The open source AI math tutor.",
    add_completion=False,
    rich_markup_mode="rich",
)


def _get(student: str):
    from euclid.core.orchestrator import Orchestrator
    return Orchestrator(student_name=student)


def _banner() -> None:
    app.print(
        Panel.fit(
            f"[bold]euclid[/bold]  [dim]v{__version__}[/dim]\n"
            "[dim]The open source AI math tutor.[/dim]",
            border_style="cyan",
        )
    )


@cli.command()
def assess(
    topic:   Optional[str] = typer.Argument(None, help="Topic or concept to assess. Omit for full placement."),
    student: str            = typer.Option("default", "--student", "-s", help="Student profile name."),
) -> None:
    """
    Map what you know. Runs a full placement if no topic is given.

    \b
    Examples:
      euclid assess
      euclid assess "fractions"
      euclid assess "algebra" --student alice
    """
    _banner()
    o = _get(student)
    try:
        o.run_assess(topic)
    finally:
        o.close()


@cli.command()
def practice(
    topic:   Optional[str] = typer.Argument(None, help="Topic to practice. Omit to use suggested next concept."),
    student: str            = typer.Option("default", "--student", "-s", help="Student profile name."),
) -> None:
    """
    Socratic dialogue on a concept. Never gives you the answer directly.

    \b
    Examples:
      euclid practice
      euclid practice "division"
      euclid practice "quadratic equations" --student alice
    """
    _banner()
    o = _get(student)
    try:
        o.run_practice(topic)
    finally:
        o.close()


@cli.command()
def explain(
    topic:   str = typer.Argument(..., help="Concept to explain from first principles."),
    student: str = typer.Option("default", "--student", "-s", help="Student profile name."),
) -> None:
    """
    Direct explanation built from what you already know.

    \b
    Examples:
      euclid explain "why do fractions flip when dividing"
      euclid explain "pythagorean theorem"
    """
    _banner()
    o = _get(student)
    try:
        o.run_explain(topic)
    finally:
        o.close()


@cli.command()
def progress(
    student: str = typer.Option("default", "--student", "-s", help="Student profile name."),
) -> None:
    """
    Your knowledge map. What you have mastered. What is unlocked next.

    \b
    Examples:
      euclid progress
      euclid progress --student alice
    """
    _banner()
    o = _get(student)
    try:
        o.run_progress()
    finally:
        o.close()


@cli.command()
def next(
    student: str = typer.Option("default", "--student", "-s", help="Student profile name."),
) -> None:
    """
    What to learn next and why.

    \b
    Examples:
      euclid next
      euclid next --student alice
    """
    _banner()
    o = _get(student)
    try:
        o.run_next()
    finally:
        o.close()


@cli.command()
def path(
    topic:   str = typer.Argument(..., help="Target concept to reach."),
    student: str = typer.Option("default", "--student", "-s", help="Student profile name."),
) -> None:
    """
    Ordered steps from where you are to a target concept.

    \b
    Examples:
      euclid path "calculus"
      euclid path "quadratic equations" --student alice
    """
    _banner()
    o = _get(student)
    try:
        o.run_path(topic)
    finally:
        o.close()


@cli.command()
def audit(
    domain:  Optional[str] = typer.Argument(None, help="Domain to audit. Omit to audit everything."),
    student: str            = typer.Option("default", "--student", "-s", help="Student profile name."),
) -> None:
    """
    Transfer-test mastered concepts to confirm real understanding.

    \b
    Examples:
      euclid audit
      euclid audit algebra
      euclid audit geometry --student alice
    """
    _banner()
    o = _get(student)
    try:
        o.run_audit(domain)
    finally:
        o.close()


@cli.command()
def setup() -> None:
    """
    Configure your LLM provider and API key.

    \b
    Supported providers:
      Anthropic  →  export ANTHROPIC_API_KEY=sk-...
      OpenAI     →  export OPENAI_API_KEY=sk-...
      Ollama     →  no key needed, runs fully offline
    """
    from rich.prompt import Prompt

    app.print("\n[bold]Setup[/bold] — configure your LLM provider\n")

    provider = Prompt.ask(
        "Provider",
        choices=["anthropic", "openai", "ollama"],
        default="anthropic",
    )

    if provider == "ollama":
        app.print(
            "\n[dim]Ollama runs fully offline. "
            "Make sure Ollama is running: [bold]ollama serve[/bold][/dim]\n"
        )
        return

    key = Prompt.ask(f"[bold]{provider.title()} API key[/bold]", password=True)
    env_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"

    from pathlib import Path
    env_file = Path.home() / ".euclid" / ".env"
    env_file.parent.mkdir(exist_ok=True)
    env_file.write_text(f"{env_var}={key}\n")

    app.print(f"\n[green]Saved[/green] → {env_file}\n")
    app.print(f"[dim]Add to your shell: [bold]export {env_var}=$(cat {env_file})[/bold][/dim]\n")


@cli.command()
def version() -> None:
    """Print version."""
    app.print(f"euclid v{__version__}")


def main() -> None:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path.home() / ".euclid" / ".env")
    cli()


if __name__ == "__main__":
    main()
