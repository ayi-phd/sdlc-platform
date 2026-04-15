import json
import subprocess
from pathlib import Path
import argparse
import uuid
import sys

# ========= CONFIG =========

AGENTS_PATH = Path("agents")
MAX_FIX_RETRIES = 2

STEPS = [
    "requirements",
    "planning",
    "implementation",
    "testing",
    "release_notes"
]

# ========= ARGS =========

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--story", required=True)
parser.add_argument("--reset", action="store_true")
args = parser.parse_args()

REPO_PATH = Path(args.repo).resolve()
SDLC_PATH = REPO_PATH / ".sdlc"

STORY_ID = args.story
STORY_PATH = SDLC_PATH / "context" / STORY_ID
ARTIFACTS = STORY_PATH / "artifacts"
STATE_FILE = STORY_PATH / "state.json"

# ========= UTIL =========

def ensure_dirs():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

def read_file(path: Path):
    return path.read_text() if path.exists() else ""

def write_artifact(name: str, content: str):
    (ARTIFACTS / f"{name}.json").write_text(content)

def read_artifact(name: str):
    return read_file(ARTIFACTS / f"{name}.json")

def load_agent(name: str):
    return (AGENTS_PATH / name / "SKILL.md").read_text()

def inject(template: str, variables: dict):
    for k, v in variables.items():
        template = template.replace(f"{{{{{k}}}}}", v or "")
    return template

# ========= STATE =========

def load_state():
    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()

    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())

    return {
        "current_step": "requirements",
        "last_completed_step": None,
        "status": "NOT_STARTED",
        "retries": 0
    }

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ========= USER INPUT =========

def ask_user_action():
    print("\nChoose action:")
    print("1) Attempt auto-fix and retest")
    print("2) Skip and continue")
    print("3) Abort")

    while True:
        choice = input("Enter choice (1/2/3): ").strip()
        if choice in ["1", "2", "3"]:
            return choice
        print("Invalid choice. Please enter 1, 2, or 3.")

# ========= CLAUDE =========

def call_claude(prompt: str):
    print("\n--- CLAUDE RUNNING ---\n")

    process = subprocess.Popen(
        ["claude", "--print", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    output = ""

    for line in process.stdout:
        print(line, end="")
        output += line

    process.wait()

    if process.returncode != 0:
        raise Exception(process.stderr.read())

    return output

def extract_json(output: str):
    import re
    matches = re.findall(r"\{.*\}", output, re.DOTALL)
    if not matches:
        raise Exception(f"No JSON in output:\n{output}")
    return json.loads(matches[-1])

def run_agent(name: str, variables: dict):
    template = load_agent(name)
    prompt = inject(template, variables)

    output = call_claude(prompt)
    parsed = extract_json(output)

    return parsed

def run_claude_code(prompt: str):
    print("\n🤖 Running Claude Code...\n")

    subprocess.run(
        ["claude", 
         "--print", 
         "--permission-mode",
         "acceptEdits",
         "-p",
         prompt],
        cwd=REPO_PATH,
        check=True
    )

# --- Run Claud Code in execution mode in order to avoid write permission issue
def run_claude_code_exec(prompt: str):
    print("\n🤖 Running Claude Code (execution mode)...\n")

    process = subprocess.Popen(
        ["claude"],
        cwd=REPO_PATH,
        stdin=subprocess.PIPE,
        text=True
    )

    process.communicate(prompt)

    if process.returncode != 0:
        raise Exception("Claude Code execution failed")

# ========= STEPS =========

def step_requirements():
    input_md = read_file(STORY_PATH / "input.md")
    if not input_md.strip():
        raise Exception("input.md is empty")

    result = run_agent("requirements", {"input": input_md})
    write_artifact("requirements", json.dumps(result, indent=2))
    return result

def step_planning():
    result = run_agent("planning", {
        "requirements": read_artifact("requirements")
    })
    write_artifact("plan", json.dumps(result, indent=2))
    return result

def step_implementation(plan=None, fix_context=None):
    template = load_agent("implementation")

    payload = {
        "plan": json.dumps(fix_context if fix_context else plan, indent=2)
    }

    prompt = inject(template, payload)

    run_claude_code(prompt)

    subprocess.run(["git", "checkout", "-B", STORY_ID], cwd=REPO_PATH)
    subprocess.run(["git", "add", "."], cwd=REPO_PATH)
    subprocess.run(["git", "commit", "-m", f"AI: {STORY_ID}"], cwd=REPO_PATH)

def step_tests():
    print("\n🧪 Running tests...\n")

    result = subprocess.run(
        ["mvn", "test"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )

    return {
        "status": "SUCCESS" if result.returncode == 0 else "FAILED",
        "output": result.stdout + result.stderr
    }

def step_test_analysis(output):
    result = run_agent("test-report-analysis", {
        "test_output": output,
        "plan": read_artifact("plan"),
        "requirements": read_artifact("requirements")
    })

    write_artifact("test_analysis", json.dumps(result, indent=2))
    return result

def step_release_notes():
    result = run_agent("release-notes", {
        "requirements": read_artifact("requirements"),
        "plan": read_artifact("plan")
    })

    (STORY_PATH / "release_notes.md").write_text(result.get("summary", ""))

# ========= MAIN =========

def main():
    ensure_dirs()
    state = load_state()

    print(f"\n🚀 SDLC RUN: {STORY_ID}")
    print(f"Resuming from: {state['current_step']}\n")

    try:
        # ===== REQUIREMENTS =====
        if state["current_step"] == "requirements":
            step_requirements()
            state.update({
                "last_completed_step": "requirements",
                "current_step": "planning"
            })
            save_state(state)
            input("\n👉 Approve requirements")

        # ===== PLANNING =====
        if state["current_step"] == "planning":
            step_planning()
            state.update({
                "last_completed_step": "planning",
                "current_step": "implementation"
            })
            save_state(state)
            input("\n👉 Approve plan")

        # ===== IMPLEMENTATION =====
        if state["current_step"] == "implementation":
            step_implementation(plan=read_artifact("plan"))
            state.update({
                "last_completed_step": "implementation",
                "current_step": "testing",
                "retries": 0
            })
            save_state(state)

        # ===== TEST LOOP WITH HUMAN CONTROL =====
        if state["current_step"] == "testing":
            while True:
                result = step_tests()

                if result["status"] == "SUCCESS":
                    print("\n✅ Tests passed\n")
                    state.update({
                        "last_completed_step": "testing",
                        "current_step": "release_notes",
                        "retries": 0
                    })
                    save_state(state)
                    break

                print("\n❌ Tests failed\n")

                analysis = step_test_analysis(result["output"])

                print("\n--- TEST ANALYSIS SUMMARY ---")
                print(analysis.get("summary", "No summary available"))

                choice = ask_user_action()

                if choice == "1":
                    if state["retries"] >= MAX_FIX_RETRIES:
                        print("\n❌ Max retries reached")
                        continue

                    if "permission" in analysis.get("summary", "").lower():
                        print("\n❌ Claude permission issue — fix CLI config first")
                        continue

                    print("\n🔁 Auto-fix attempt...\n")

                    step_implementation(fix_context=analysis)

                    state["retries"] += 1
                    save_state(state)

                    continue

                elif choice == "2":
                    print("\n⚠️ Skipping tests — continuing pipeline\n")
                    state.update({
                        "last_completed_step": "testing",
                        "current_step": "release_notes"
                    })
                    save_state(state)
                    break

                elif choice == "3":
                    print("\n🛑 Aborting SDLC flow\n")
                    state["status"] = "ABORTED"
                    save_state(state)
                    sys.exit(1)

        # ===== RELEASE =====
        if state["current_step"] == "release_notes":
            step_release_notes()
            state["status"] = "DONE"
            save_state(state)

        print("\n🎉 SDLC COMPLETE\n")

    except Exception as e:
        print(f"\n❌ FAILURE: {e}")
        save_state(state)
        sys.exit(1)

# ========= ENTRY =========

if __name__ == "__main__":
    main()