import os
import time
import json
import subprocess
from pathlib import Path
import argparse
import sys
from modules.deploy_to_test import deploy_to_test

##from dotenv import load_dotenv
from modules.pr_review_stage import run_pr_review_stage

# ========= CONFIG =========

AGENTS_PATH = Path("agents")
MAX_FIX_RETRIES = 2

CONFIG = {
    "enable_ai_pr_review": True,
    "require_approval": False,
    "auto_merge_on_pass": False,
    "max_fix_iterations": 3,

    "deploy_host": "35.88.13.248",
    "deploy_user": "ec2-user",
    "deploy_key": "~/.ssh/unicorn-key-pair-prod.pem"
}

# Load secret keys from .env file
##load_dotenv()
##CONFIG["github_token"] = os.getenv("GITHUB_TOKEN")

# Helper to get remote repo info
def get_repo_info(repo_path):
    result = subprocess.check_output(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_path,
        text=True
    ).strip()

    if result.startswith("git@"):
        path = result.split(":", 1)[1]
    else:
        path = result.split("github.com/")[1]

    path = path.replace(".git", "")
    owner, repo = path.split("/", 1)

    return owner, repo

# Workflow steps
STEPS = [
    "requirements",
    "planning",
    "implementation",
    "testing",
    "git_prepare",
    "create_pr",
    "pr_review",
    "deploy_to_test",
    "release_notes"
]

# ========= ARGS =========

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--story", required=True)
parser.add_argument("--reset", action="store_true")
args = parser.parse_args()

REPO_PATH = Path(args.repo).resolve()

# Set repo info
owner, repo = get_repo_info(REPO_PATH)
CONFIG["repo_owner"] = owner
CONFIG["repo_name"] = repo
print(f"🔗 Repo detected: {owner}/{repo}")

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

def load_agent_skill(name: str):
    return (AGENTS_PATH / name / "SKILL.md").read_text()

def inject(template: str, variables: dict):
    for k, v in variables.items():
        template = template.replace(f"{{{{{k}}}}}", v or "")
    return template

def get_branch_name():
    return STORY_ID.lower()

def branch_exists_remote(branch):
    result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())

# ========= STATE =========

def load_state():
    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()

    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())

    return {
        "current_step": "requirements",
        "status": "NOT_STARTED",
        "retries": 0,
        "pr_number": None
    }

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def next_step(current):
    idx = STEPS.index(current)
    return STEPS[idx + 1] if idx + 1 < len(STEPS) else None

# ========= CLAUDE =========

def call_claude(prompt: str, stream: bool = True):
    ####if stream:
    print("\n--- CLAUDE RUNNING ---\n")

    process = subprocess.Popen(
        ["claude", "--print", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    output = ""

    # -----------------------------
    # STREAMING MODE
    # -----------------------------
    if stream:
        for line in process.stdout:
            print(line, end="")
            output += line

    # -----------------------------
    # NON-STREAM MODE
    # -----------------------------
    else:
        stdout, stderr = process.communicate()
        output = stdout

        if process.returncode != 0:
            raise Exception(stderr)

        return output

    # -----------------------------
    # FINALIZE
    # -----------------------------
    process.wait()

    if process.returncode != 0:
        raise Exception(process.stderr.read())

    return output

def extract_json(output: str):
    import re
    matches = re.findall(r"\{.*\}", output, re.DOTALL)
    if not matches:
        raise Exception("No JSON found")
    return json.loads(matches[-1])

def run_agent(name: str, variables: dict):
    template = load_agent_skill(name)
    prompt = inject(template, variables)
    return extract_json(call_claude(prompt))

def run_claude_code(prompt: str):
    print("\n--- CLAUDE CODE RUNNING ---\n")
    subprocess.run(
        ["claude", "--print", "--permission-mode", "acceptEdits", "-p", prompt],
        cwd=REPO_PATH,
        check=True
    )

# ========= STEP FUNCTIONS =========

def build_repo_context_full(repo_path):
    file_list = []

    for root, _, files in os.walk(repo_path):
        for f in files:
            full_path = os.path.join(root, f)

            # ✅ KEY: make path relative to target repo
            rel_path = os.path.relpath(full_path, repo_path)

            file_list.append(rel_path)

    return file_list, {}

def step_requirements(state):
    input_md = read_file(STORY_PATH / "input.md")
    result = run_agent("requirements", {"input": input_md})
    write_artifact("requirements", json.dumps(result, indent=2))
    input("\n👉 Approve requirements")
    return next_step("requirements")

def step_planning(state):
    print("\n🔍 Detecting tech stack...\n")

    # -----------------------------
    # Build repo context
    # -----------------------------
    files, contents = build_repo_context_full(REPO_PATH)

    stack_prompt = f"""
You are analyzing a code repository.

You DO NOT have filesystem access.
Use ONLY the provided data.

FULL repository file list:
{files}

Sample file contents:
{json.dumps(contents, indent=2)}

Return STRICT JSON:

{{
  "backend": "...",
  "frontend": "...",
  "frameworks": [],
  "languages": [],
  "build_tools": "...",
  "notes": "..."
}}
"""

    stack_output = call_claude(stack_prompt, stream=False)
    stack = extract_json(stack_output)

    print("\n🧠 Detected stack:")
    print(json.dumps(stack, indent=2))

    # Save it (optional but useful)
    write_artifact("stack", json.dumps(stack, indent=2))

    # -----------------------------
    # Planning step (WITH STACK)
    # -----------------------------
    files_str = "\n".join(files)

    result = run_agent("planning", {
        "requirements": read_artifact("requirements"),
        "stack": json.dumps(stack, indent=2),
        "files": files_str
    })

    write_artifact("plan", json.dumps(result, indent=2))

    input("\n👉 Approve plan")
    return next_step("planning")

def step_implementation(state):
    plan = read_artifact("plan")

    prompt = inject(load_agent_skill("implementation"), {
        "plan": plan
    })

    run_claude_code(prompt)

    return next_step("implementation")

def step_testing(state):
    while True:
        result = subprocess.run(
            ["mvn", "test"],
            cwd=REPO_PATH,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("\n✅ Tests passed\n")
            state["retries"] = 0
            return next_step("testing")

        print("\n❌ Tests failed\n")

        analysis = run_agent("test-report-analysis", {
            "test_output": result.stdout + result.stderr,
            "plan": read_artifact("plan"),
            "requirements": read_artifact("requirements")
        })

        print("\n--- TEST ANALYSIS ---")
        print(analysis.get("summary", ""))

        choice = input("\n1) Fix  2) Skip  3) Abort: ")

        if choice == "1":
            if state["retries"] >= MAX_FIX_RETRIES:
                print("Max retries reached")
                continue

            run_claude_code(inject(load_agent_skill("implementation"), {
                "plan": json.dumps(analysis, indent=2)
            }))

            state["retries"] += 1
            continue

        elif choice == "2":
            return next_step("testing")

        else:
            sys.exit(1)

def step_git_prepare(state):
    branch = get_branch_name()

    print(f"\n🌿 Preparing git branch: {branch}")

    exists_remote = branch_exists_remote(branch)

    if exists_remote:
        print("🔁 Remote branch exists — syncing")

        # fetch latest remote state
        subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=REPO_PATH,
            check=True
        )

        # checkout branch (track remote)
        subprocess.run(
            ["git", "checkout", branch],
            cwd=REPO_PATH,
            check=True
        )

        # optional: rebase onto remote (safe sync)
        subprocess.run(
            ["git", "rebase", f"origin/{branch}"],
            cwd=REPO_PATH,
            check=True
        )

    else:
        print("🆕 Creating new branch")

        subprocess.run(
            ["git", "checkout", "-B", branch],
            cwd=REPO_PATH,
            check=True
        )

    # -----------------------------
    # Commit changes (if any)
    # -----------------------------
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )

    if result.stdout.strip():
        subprocess.run(
            ["git", "add", "."],
            cwd=REPO_PATH,
            check=True
        )

        subprocess.run(
            ["git", "commit", "-m", f"AI: {branch}"],
            cwd=REPO_PATH,
            check=True
        )

        print("✅ Changes committed")
    else:
        print("ℹ️ No changes to commit")

    # -----------------------------
    # Push logic
    # -----------------------------
    if exists_remote:
        print("⬆️ Pushing updates to existing branch")
        subprocess.run(
            ["git", "push"],
            cwd=REPO_PATH,
            check=True
        )
    else:
        print("🚀 Pushing new branch to origin")
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=REPO_PATH,
            check=True
        )

    return next_step("git_prepare")

def get_current_branch():
    result = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=REPO_PATH,
        text=True
    )
    return result.strip()

def create_pr():
    # 1. Resolve REPO_PATH to get the folder name dynamically
    # os.path.abspath handles relative paths like '../unicorn-spring-ai-agent'
    abs_path = os.path.abspath(REPO_PATH)
    repo_folder = os.path.basename(abs_path)
    repo_name = f"ayi-phd/{repo_folder}"

    # 2. Extract branch info
    head_branch = get_current_branch().strip()
    base_branch = "develop"

    print(f"\n=== STEP: CREATE_PR ===")
    print(f"DEBUG: REPO_PATH (raw): {REPO_PATH}")
    print(f"DEBUG: REPO_PATH (resolved): {abs_path}")
    print(f"DEBUG: Derived Repo Name: {repo_name}")
    print(f"DEBUG: Head Branch: {head_branch}")
    print(f"DEBUG: GITHUB_TOKEN in Env: {'FOUND' if 'GITHUB_TOKEN' in os.environ else 'NOT FOUND'}")

    # 3. Sanitize Environment
    # We remove the GITHUB_TOKEN so 'gh' uses your authenticated Mac session
    clean_env = os.environ.copy()
    if "GITHUB_TOKEN" in clean_env:
        print(f"DEBUG: Scrubbing GITHUB_TOKEN from subprocess environment.")
        del clean_env["GITHUB_TOKEN"]
    clean_env.pop("GH_TOKEN", None)

    # 4. Execution with Retry Loop
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        print(f"🔗 Attempt {attempt}: Creating PR via GH Wrapper for {repo_name}...")
        
        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--repo", repo_name,
                "--base", base_branch,
                "--head", head_branch,
                "--title", f"AI: {head_branch}",
                "--body", "Automated PR created by run.py"
            ],
            cwd=REPO_PATH,
            capture_output=True,
            text=True,
            env=clean_env
        )

        if result.returncode == 0:
            pr_url = result.stdout.strip()
            print(f"✅ PR Created Successfully: {pr_url}")
            return pr_url.split("/")[-1]
        
        # Capture failure details
        stderr = result.stderr.strip()
        print(f"DEBUG: Attempt {attempt} failed.")
        print(f"DEBUG: STDERR: {stderr}")

        # Check for indexing lag
        if any(err in stderr.lower() for err in ["sha", "no commits", "not found"]):
            print(f"⏳ GitHub indexing lag suspected. Retrying in 5s...")
            time.sleep(5)
        else:
            print(f"❌ Permanent Error Encountered.")
            break

    raise Exception(f"FAILURE: Failed to create PR for {repo_name} after {max_retries} attempts.")

def step_create_pr(state):
    if not state.get("pr_number"):
        pr_number = create_pr()
        state["pr_number"] = pr_number
        print(f"🔗 PR created: #{pr_number}")
    return next_step("create_pr")

def step_pr_review(state):
    pr_number = state.get("pr_number")
    if not pr_number:
        raise Exception("Missing PR number")

    merged = run_pr_review_stage(CONFIG, pr_number)

    state["merged"] = merged   # 👈 THIS IS THE FIX

    if not merged:
        print("❌ PR not merged")
        sys.exit(1)

    return next_step("pr_review")

def step_release_notes(state):
    print("\n📝 Generating release notes...\n")

    # -----------------------------
    # Get actual code changes
    # -----------------------------
    diff = subprocess.check_output(
        ["git", "diff", "origin/develop~1", "origin/develop"],
        cwd=REPO_PATH,
        text=True
    )

    prompt = f"""
    Generate concise release notes (1–5 sentences) based on the following code changes.

    Focus on:
    - user-visible changes
    - feature behavior
    - bug fixes

    Do NOT describe internal tooling or pipelines.

    Code diff:
    {diff[:12000]}
    """

    output = call_claude(prompt)

    (STORY_PATH / "release_notes.md").write_text(output.strip())

    state["status"] = "DONE"
    return None

def step_deploy_to_test(state):
    return deploy_to_test(state, REPO_PATH, CONFIG)

# ========= STEP REGISTRY =========

STEP_HANDLERS = {
    "requirements": step_requirements,
    "planning": step_planning,
    "implementation": step_implementation,
    "testing": step_testing,
    "git_prepare": step_git_prepare,
    "create_pr": step_create_pr,
    "pr_review": step_pr_review,
    "deploy_to_test": step_deploy_to_test,
    "release_notes": step_release_notes
}

# ========= MAIN =========

def main():
    ensure_dirs()
    state = load_state()

    print(f"\n🚀 SDLC RUN: {STORY_ID}")
    print(f"Starting at: {state['current_step']}\n")

    try:
        while state["current_step"]:
            step = state["current_step"]
            print(f"\n=== STEP: {step.upper()} ===\n")

            handler = STEP_HANDLERS[step]
            next_s = handler(state)

            state["current_step"] = next_s
            save_state(state)

        print("\n🎉 SDLC COMPLETE\n")

    except Exception as e:
        print(f"\n❌ FAILURE: {e}")
        save_state(state)
        sys.exit(1)


if __name__ == "__main__":
    main()