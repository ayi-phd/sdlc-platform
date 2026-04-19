import os
import sys
import time
import json
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from modules.deploy_to_test import deploy_to_test
from modules.pr_review_stage import run_pr_review_stage
from modules.utils import run_claude, extract_json, load_agent_skill, inject, run_claude_code


@dataclass
class StepResult:
    status: str = "success"
    data: dict = field(default_factory=dict)

# ========= CONFIG =========

MAX_FIX_RETRIES = 2

CONFIG = {
    "enable_ai_pr_review": True,
    "require_approval": False,
    "auto_merge_on_pass": False,
    "max_fix_iterations": 3,

    # Deploy credentials — override via environment variables to avoid
    # committing host/key details into version control.
    "deploy_host": os.getenv("DEPLOY_HOST", "35.88.13.248"),
    "deploy_user": os.getenv("DEPLOY_USER", "ec2-user"),
    "deploy_key": os.getenv("DEPLOY_KEY", "~/.ssh/unicorn-key-pair-prod.pem"),
}

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

# ========= CLAUDE =========

def run_agent(name: str, variables: dict):
    template = load_agent_skill(name)
    prompt = inject(template, variables)
    return extract_json(run_claude(prompt, cwd=REPO_PATH))

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
    return StepResult()

def step_planning(state):
    print("\n🔍 Detecting tech stack...\n")

    # -----------------------------
    # Build repo context
    # -----------------------------
    files, contents = build_repo_context_full(REPO_PATH)

    stack_prompt = inject(load_agent_skill("repo-analysis"), {
        "files": str(files),
        "contents": json.dumps(contents, indent=2),
    })

    stack_output = run_claude(stack_prompt, stream=False, cwd=REPO_PATH)
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
    return StepResult()

def step_implementation(state):
    plan = read_artifact("plan")

    prompt = inject(load_agent_skill("implementation"), {
        "plan": plan
    })

    run_claude_code(prompt, cwd=REPO_PATH)

    return StepResult()

def step_testing(state):
    while True:
        print("\n--- RUNNING UNIT TESTS ---\n")
        result = subprocess.run(
            ["mvn", "test"],
            cwd=REPO_PATH,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("\n✅ Tests passed\n")
            state["retries"] = 0
            return StepResult()

        print("\n❌ Tests failed\n")

        analysis = run_agent("test-report-analysis", {
            "test_output": result.stdout + result.stderr,
            "plan": read_artifact("plan"),
            "requirements": read_artifact("requirements")
        })

        print("\n--- TEST ANALYSIS ---")
        print(analysis.get("summary", ""))

        choice = input("\n👉 1) Fix  2) Skip  3) Abort: ")

        if choice == "1":
            if state["retries"] >= MAX_FIX_RETRIES:
                print("Max retries reached")
                continue

            run_claude_code(inject(load_agent_skill("implementation"), {
                "plan": json.dumps(analysis, indent=2)
            }), cwd=REPO_PATH)

            state["retries"] += 1
            continue

        elif choice == "2":
            return StepResult()

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

    return StepResult()

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

    # 3. Sanitize Environment
    # We remove the GITHUB_TOKEN so 'gh' uses your authenticated Mac session
    clean_env = os.environ.copy()
    if "GITHUB_TOKEN" in clean_env:
        print(f"DEBUG: Scrubbing GITHUB_TOKEN from subprocess environment.")
        del clean_env["GITHUB_TOKEN"]
    clean_env.pop("GH_TOKEN", None)

    #print(f"DEBUG: REPO_PATH (raw): {REPO_PATH}")
    #print(f"DEBUG: REPO_PATH (resolved): {abs_path}")
    #print(f"DEBUG: Derived Repo Name: {repo_name}")
    #print(f"DEBUG: Head Branch: {head_branch}")
    #print(f"DEBUG: GITHUB_TOKEN in Env: {'FOUND' if 'GITHUB_TOKEN' in os.environ else 'NOT FOUND'}")

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
    return StepResult()

def step_pr_review(state):
    pr_number = state.get("pr_number")
    if not pr_number:
        raise Exception("Missing PR number")

    merged = run_pr_review_stage(CONFIG, pr_number, repo_path=REPO_PATH)

    state["merged"] = merged   # 👈 THIS IS THE FIX

    if not merged:
        print("❌ PR not merged")
        sys.exit(1)

    return StepResult()

def step_deploy_to_test(state):
    input("\n👉 Approve deployment")
    deploy_to_test(state, REPO_PATH, CONFIG)
    return StepResult()

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

    prompt = inject(load_agent_skill("release-notes"), {"diff": diff[:12000]})

    output = run_claude(prompt, cwd=REPO_PATH)

    (STORY_PATH / "release_notes.md").write_text(output.strip())

    return StepResult()

# =========== ORDERED STEPS LIST ===========

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

# ========= STEP FUNCTIONS REGISTRY =========

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
        idx = STEPS.index(state["current_step"])

        while idx < len(STEPS):
            step = STEPS[idx]
            print(f"\n=== STEP {idx}: {step.upper()} ===\n")

            STEP_HANDLERS[step](state)

            idx += 1
            state["current_step"] = STEPS[idx] if idx < len(STEPS) else None
            save_state(state)

        state["status"] = "DONE"
        save_state(state)
        print("\n🎉 SDLC COMPLETE\n")

    except Exception as e:
        print(f"\n❌ FAILURE: {e}")
        save_state(state)
        sys.exit(1)


if __name__ == "__main__":
    main()