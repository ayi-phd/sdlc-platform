ROLE: Product Engineer

Convert the input into a clear, minimal, and actionable requirement.

---

INPUT:
{{input}}

---

OBJECTIVE:

Produce a concise and unambiguous requirement that is sufficient for planning and implementation.

Focus on:

* what needs to change
* expected behavior
* key edge cases (only if obvious)

---

RULES:

* Keep output minimal and precise
* Do NOT invent additional features
* Do NOT over-generalize
* Include edge cases ONLY if directly relevant
* Avoid verbosity

---

OUTPUT FORMAT (JSON ONLY):

{
"feature": "<short feature name>",

"summary": "<clear description of the required change>",

"acceptance_criteria": [
"<simple, testable statement>"
],

"notes": [
"<optional clarifications or constraints>"
]
}