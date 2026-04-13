<p align="center">
  <img src="assets/hero.png" alt="Euclid CLI" width="800" />
</p>
<p align="center">The open source AI math tutor.</p>
<p align="center">
  <a href="#"><img alt="License" src="https://img.shields.io/badge/license-MIT-0d9668?style=flat-square" /></a>
  <a href="#"><img alt="Python" src="https://img.shields.io/badge/python-3.10+-0d9668?style=flat-square" /></a>
  <a href="#"><img alt="Version" src="https://img.shields.io/badge/version-0.1.0-0d9668?style=flat-square" /></a>
</p>

---

### Installation

```bash
git clone https://github.com/Tarek-new/euclid.git
cd euclid
pip install -e .
euclid setup
```

Supports Anthropic, OpenAI, and Ollama (fully offline). Run `euclid setup` to configure.

---

### What you type → what happens

```
$ euclid assess
→ Tests 8 concepts across grade levels, finds exactly where you are

$ euclid assess "fractions"
→ Assesses one concept with a real problem, maps your knowledge state

$ euclid practice
→ Socratic dialogue on your next suggested concept — never gives the answer

$ euclid practice "quadratic equations"
→ Socratic dialogue on a specific concept, followed by a transfer check

$ euclid explain "why do fractions flip when dividing"
→ Direct explanation built from what you already know

$ euclid progress
→ Your knowledge map — mastered, in progress, unlocked next

$ euclid next
→ What to learn next and why, with a real-world use case

$ euclid path "calculus"
→ Ordered sequence of every concept between you and calculus

$ euclid audit
→ Transfer-tests all mastered concepts to confirm real understanding
```

---

### Commands

| Command | What it does |
| --- | --- |
| `assess [topic]` | Map your knowledge. Full placement if no topic given. |
| `practice [topic]` | Socratic dialogue. Never tells you the answer. |
| `explain <topic>` | Direct explanation from first principles. |
| `progress` | Knowledge map with domain breakdown and progress bars. |
| `next` | What to learn next and why. |
| `path <topic>` | Ordered steps from where you are to any target concept. |
| `audit [domain]` | Transfer-test mastered concepts. Catches pattern memorisation. |
| `setup` | Configure LLM provider and API key. |

---

### Agents

Four agents, dispatched automatically.

- **Assessor** — maps what you know through targeted problems, not multiple choice
- **Navigator** — determines what you are ready to learn next using knowledge space theory
- **Socrates** — guides you to answers through questions, never gives them directly
- **Verifier** — confirms mastery is real by testing transfer to a different context

---

### How it works

Built on [LangGraph](https://github.com/langchain-ai/langgraph) for multi-agent orchestration and [LiteLLM](https://github.com/BerriAI/litellm) for pluggable LLM support. The knowledge graph encodes 60 math concepts from grade 1 through calculus with their prerequisite dependencies — derived from [Knowledge Space Theory](https://link.springer.com/book/10.1007/978-3-642-58625-5) (Doignon & Falmagne, 1999). Every session is stored locally in `~/.euclid/state.db`. No data leaves your machine except LLM API calls.

---

### Knowledge graph

60 concepts. Grades 1 through 12. Five domains.

| Domain | Concepts |
| --- | --- |
| Arithmetic | Counting → Place value → Operations → Fractions → Decimals |
| Algebra | Expressions → Equations → Functions → Polynomials → Logarithms |
| Geometry | Shapes → Angles → Proofs → Trigonometry |
| Statistics | Center/spread → Probability → Inference |
| Calculus | Limits → Derivatives → Integrals |

---

### Multiple students

```bash
euclid assess --student alice
euclid practice --student bob
euclid progress --student alice
```

Each student profile is stored separately in `~/.euclid/state.db`.

---

### Offline mode

Run fully offline with [Ollama](https://ollama.com):

```bash
ollama serve
ollama pull qwen2.5:7b
euclid setup   # choose Ollama
```

No API key. No internet. No cost.

---

### Why Euclid

ALEKS charges $50 per student per year to do three things: find out what a student knows, decide what they are ready to learn next, and give targeted practice. Euclid does all three — free, open source, and better, because it uses conversation instead of multiple choice and tests real understanding instead of pattern recall.

---

### Contributing

```bash
git clone https://github.com/Tarek-new/euclid.git
cd euclid
pip install -e ".[dev]"
pytest
```

---

[MIT License](LICENSE)
