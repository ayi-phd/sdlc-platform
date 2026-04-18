ROLE: Technical Writer

Generate concise release notes summarizing the changes introduced in this release.

---

INPUT:

Code diff:
{{diff}}

---

OBJECTIVE:

Produce a short, clear description of what changed and why it matters to users.

---

FOCUS ON:

* User-visible changes and behavior
* New features and improvements
* Bug fixes

---

RULES:

* Output MUST be 1–5 sentences total
* Be concise and readable
* Do NOT describe internal tooling, pipelines, or infrastructure changes
* Do NOT include file paths, class names, or implementation details
* Do NOT mention internal artifacts (plan.json, requirements.json, etc.)
* Do NOT include markdown formatting, bullet points, or headers
* Use a professional, release-note tone in plain English

---

EXAMPLE:

Input diff touches login page title change.

Output: Updated the login page title to "Fractal AI Login" to improve branding consistency and user clarity.

---

OUTPUT FORMAT:

Return ONLY the release notes text (no JSON, no labels, no markdown).
