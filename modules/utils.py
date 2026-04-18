import subprocess
import json
from pathlib import Path

# Resolved relative to this file so callers don't depend on the working directory.
_AGENTS_PATH = Path(__file__).parent.parent / "agents"


def call_claude(prompt: str, stream: bool = True) -> str:
    """Invoke the Claude CLI and return the full output.

    Streaming mode prints each line as it arrives; non-streaming mode waits
    for the process to finish before returning.  Both modes raise on a
    non-zero exit code.
    """
    print("\n--- CLAUDE RUNNING ---\n")

    process = subprocess.Popen(
        ["claude", "--print", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output = ""

    if stream:
        for line in process.stdout:
            print(line, end="")
            output += line
        # communicate() drains any remaining stderr and calls wait() internally,
        # which avoids the deadlock that arises when stderr fills its OS pipe
        # buffer while we're still reading stdout.
        _, err = process.communicate()
        if process.returncode != 0:
            raise Exception(f"Claude exited with non-zero status:\n{err}")
    else:
        stdout, err = process.communicate()
        output = stdout
        if process.returncode != 0:
            raise Exception(f"Claude exited with non-zero status:\n{err}")

    return output


def extract_json(output: str) -> dict:
    """Extract the last valid JSON object from Claude output.

    Uses balanced-brace parsing instead of a greedy regex so nested objects
    are handled correctly.  Tries candidates from last to first because
    Claude typically places the final JSON block at the end of its response.
    """
    blocks: list[str] = []
    depth = 0
    start = None

    for i, ch in enumerate(output):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(output[start : i + 1])

    if not blocks:
        raise ValueError(
            f"No JSON object found in Claude output:\n{output[:500]}"
        )

    for candidate in reversed(blocks):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError(
        "Claude output contained JSON-like blocks but none were valid JSON."
        f"\n{output[:500]}"
    )


def load_agent_skill(name: str, agents_path: Path = _AGENTS_PATH) -> str:
    """Load a SKILL.md prompt template by agent name."""
    return (agents_path / name / "SKILL.md").read_text()


def inject(template: str, variables: dict) -> str:
    """Replace {{key}} placeholders in a prompt template."""
    for k, v in variables.items():
        template = template.replace(f"{{{{{k}}}}}", v or "")
    return template
