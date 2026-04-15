import json
import subprocess
from pathlib import Path
import argparse
import uuid

# ========= CONFIG =========

AGENTS_PATH = Path("agents")
MAX_FIX_RETRIES = 2

# ========= ARGS =========

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--story", default=None)
args = parser.parse_args()

REPO_PATH = Path(args.repo).resolve()
SDLC_PATH = REPO_PATH / ".sdlc"

STORY_ID = args.story or f"story-{uuid.uuid4().hex[:6]}"
STORY_PATH = SDLC_PATH / "context" / STORY_ID
ARTIFACTS = STORY_PATH / "artifacts"
LOGS = STORY_PATH / "logs"

# ========= UTIL =========

def ensure_dirs():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

def log(step, data):
    (LOGS / f"{step}.json").write_text(json.dumps(data, indent=2))

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

# ========= CLAUDE CLI =========

def call_claude(prompt: str):
    print("\n--- CLAUDE PROMPT (truncated) ---\n")
    print(prompt[:800])

    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True
    )

    output = result.stdout.strip()

    if not output:
        raise Exception("Empty response from Claude")

    return output

def extract_json(output: str):
    try:
        start = output.find("{")
        end = output.rfind("}") + 1
        return json.loads(output[start:end])
    except Exception:
        raise Exception(f"Failed to parse JSON:\n{output}")

def run_agent(name: str, variables: dict):
    template = load_agent(name)
    prompt = inject(template, variables)

    output = call_claude(prompt)
    parsed = extract_json(output)

    log(name, parsed)
    return parsed

# ========= CLAUDE CODE EXECUTION =========

def run_claude_code(prompt: str):
    print("\n🤖 Running Claude Code...\n")

    subprocess.run(
        ["claude", "--print", prompt],
        cwd=REPO_PATH,
        check=True
    )

# ========= STEPS =========

def step_requirements():
    input_md = read_file(STORY_PATH / "input.md")

    result = run_agent("requirements", {
        "input": input_md
    })

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

    payload = {}

    if fix_context:
        payload["plan"] = json.dumps(fix_context, indent=2)
    else:
        payload["plan"] = plan

    prompt = inject(template, payload)

    run_claude_code(prompt)

    subprocess.run(["git", "checkout", "-B", f"{STORY_ID}"], cwd=REPO_PATH)
    subprocess.run(["git", "add", "."], cwd=REPO_PATH)
    subprocess.run(
        ["git", "commit", "-m", f"AI: {STORY_ID}"],
        cwd=REPO_PATH
    )

    return {"status": "SUCCESS"}

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

def step_test_analysis(test_output):
    result = run_agent("test-report-analysis", {
        "test_output": test_output,
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

    (STORY_PATH / "release_notes.md").write_text(
        result.get("summary", "")
    )

    return result

# ========= FLOW =========

def main():
    ensure_dirs()

    print(f"\n🚀 SDLC RUN: {STORY_ID}\n")

    # 1. Requirements
    step_requirements()
    input("\n👉 Approve requirements? (Enter to continue)")

    # 2. Planning
    step_planning()
    input("\n👉 Approve plan? (Enter to continue)")

    # 3. Implementation
    plan = read_artifact("plan")
    step_implementation(plan=plan)

    # 4. Test + Fix Loop
    retries = 0

    while True:
        test_result = step_tests()

        if test_result["status"] == "SUCCESS":
            print("\n✅ Tests passed\n")
            break

        print("\n❌ Tests failed\n")

        analysis = step_test_analysis(test_result["output"])

        action = analysis.get("recommendation", {}).get("action")

        if action != "RETRY_FIX":
            print("\n⚠️ Escalating to human\n")
            input("Fix manually, then press Enter...")
            break

        if retries >= MAX_FIX_RETRIES:
            print("\n❌ Max retries reached\n")
            break

        print("\n🔁 Auto-fix attempt...\n")

        step_implementation(fix_context=analysis)

        retries += 1

    # 5. Release Notes
    step_release_notes()

    print("\n🎉 SDLC COMPLETE\n")

# ========= ENTRY =========

if __name__ == "__main__":
    main()
