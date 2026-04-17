# SKILL: Generate Release Notes (Brief)

## Goal

Produce concise release notes (1–5 sentences) summarizing the change introduced in this PR.

---

## Inputs

* `requirements` — original user story / intent
* `plan` — high-level implementation approach
* `pr_number` — pull request identifier
* `review_summary` (optional) — AI review summary

---

## Instructions

Generate a short, clear summary of what changed and why.

Focus on:

* The user-facing impact or behavior change
* The main feature, fix, or improvement
* Any important context (if relevant)

---

## Rules

* Output MUST be **1–5 sentences total**
* Be concise and readable
* Do NOT include implementation details (no file paths, classes, or code)
* Do NOT mention internal artifacts (plan.json, requirements.json, etc.)
* Do NOT include markdown formatting
* Do NOT include bullet points

---

## Style

* Professional, release-note tone
* Clear and direct
* Prefer plain English over technical jargon

---

## Output Format

Return ONLY the release notes text (no JSON, no labels)

---

## Example

Input:

* requirements: "Rename login page title to 'Fractal AI Login'"

Output:
Updated the login page title to “Fractal AI Login” to improve branding consistency and user clarity.