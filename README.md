# 🚀 AI-Augmented SDLC Orchestrator

A deterministic, multi-agent system that automates the software development lifecycle — from raw requirements to tested code — reducing cognitive load on engineers, while keeping them in control at key decision points.

---

## 🧠 What This Is

This project explores a structured alternative to “vibe coding”:

> **AI executes. Engineers decide.**

Instead of one-shot prompts, the system breaks SDLC into **independent agents**, each responsible for a single phase, coordinated by a **stateful orchestrator**.

---

## ⚙️ How It Works

```
Requirements → Planning → Implementation → Testing/Fix Loop → PR creation/AI Review/Merge → Release
```

- Each step is handled by a dedicated AI agent (`SKILL.md`)
- A Python orchestrator (`run.py`) enforces flow and state
- All context is persisted to disk (`.sdlc/context/...`)
- Execution is **resumable and deterministic**

---

## 🔁 Key Features

- **Liner, Multi-Agent Architecture**  
  Independent agents for requirements, planning, implementation, testing, and release

- **Stateful Execution**  
  Progress tracked via `state.json` → resume anytime

- **Pre-Review by AI**
  Leverage AI to pre-review test excution results and PRs

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

- **Automated Deployment**
  After successful completion and code check-in, auto deploy to cloud 

---

## 🧩 Project Structure

```
sdlc-platform/
  agents/          # AI agents (prompt contracts)
  modules/         # Stage-specific functions
  run.py           # Orchestrator

Demo WebApp:

unicorn-spring-ai-agent/
  .sdlc/context/                   # State, artifacts, logs
    FEATURE-UNI-019-user-login     #
      artifacts                    # Step artifacts
      input.md                     # Feature requirements
  src/                             # Application code
```

---

## 🧪 Example execution

```bash
python3 run.py --repo ../unicorn-spring-ai-agent --story FEATURE-UNI-019-user-login --clean-output --skip-approvals
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
  Reliable AI systems are based on deterministic workflows

- **State > File**  
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

> **Keep determenistic workflow, Leverage AI at what it does best (code & docs generation, analysis & review)**

This project can be used directly in enterprise orgs to increase velocity while maintaining or reducing risk profile.
