# 🚀 AI-Augmented SDLC Orchestrator

A deterministic, multi-agent system that automates the software development lifecycle — from raw requirements to tested code — while keeping engineers in control at key decision points.

---

## 🧠 What This Is

This project explores a structured alternative to “vibe coding”:

> **AI executes. Engineers decide.**

Instead of one-shot prompts, the system breaks SDLC into **independent agents**, each responsible for a single phase, coordinated by a **stateful orchestrator**.

---

## ⚙️ How It Works

```
Requirements → Planning → Implementation → Testing → Fix Loop → Release
```

- Each step is handled by a dedicated AI agent (`SKILL.md`)
- A Python orchestrator (`run.py`) enforces flow and state
- All context is persisted to disk (`.sdlc/context/...`)
- Execution is **resumable and deterministic**

---

## 🔁 Key Features

- **Multi-Agent Architecture**  
  Independent agents for requirements, planning, implementation, testing, and release

- **Stateful Execution**  
  Progress tracked via `state.json` → resume anytime

- **Human-in-the-Loop Control**  
  At failure points:
  ```
  1) Auto-fix and retry
  2) Skip and continue
  3) Abort
  ```

- **Real Code Execution**  
  - Uses Claude Code to modify actual repositories  
  - Runs real test suites (`mvn test`)  

- **Git-Integrated Workflow**  
  Each story runs on its own branch with traceable commits

---

## 🧩 Project Structure

```
sdlc-platform/
  agents/          # AI agents (prompt contracts)
  run.py           # Orchestrator

auth-server/
  .sdlc/context/   # State, artifacts, logs
  src/             # Application code
```

---

## 🧪 Example Run

```bash
python run.py --repo ../auth-server --story AUTH-009-test
```

```
❌ Tests failed

Choose action:
1) Attempt auto-fix and retest
2) Skip and continue
3) Abort
```

---

## 🧠 Key Ideas

- **Structure > Prompting**  
  Reliable AI systems need workflows, not just prompts

- **State > Memory**  
  Everything is explicit, persisted, and resumable

- **Isolation > Complexity**  
  Unit-test-driven flow avoids fragile infra dependencies

---

## 🚀 Why It Matters

This project demonstrates:

- AI-assisted engineering workflows  
- Deterministic orchestration of LLM agents  
- Practical boundaries between automation and human control  

---

## ⭐ Takeaway

> **Software development is a system — not a prompt.**

This project brings that system into the AI era.
