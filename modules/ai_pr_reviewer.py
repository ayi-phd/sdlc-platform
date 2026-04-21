import subprocess
import json

from modules.utils import run_claude, extract_json, load_agent_skill, inject


class AiPrReviewer:
    def __init__(self, owner, repo, repo_path=None):
        self.owner = owner
        self.repo = repo
        self.repo_path = repo_path

    # -----------------------------
    # GitHub via GH CLI
    # -----------------------------

    def gh_api(self, args, input_data=None):
        cmd = ["gh", "api"] + args

        result = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise Exception(f"GH API error:\n{result.stderr}")

        return result.stdout

    def get_pr_diff(self, pr_number):
        return self.gh_api(
            [
                f"repos/{self.owner}/{self.repo}/pulls/{pr_number}",
                "--header", "Accept: application/vnd.github.v3.diff"
            ]
        )

    def get_pr_details(self, pr_number):
        output = self.gh_api(
            [f"repos/{self.owner}/{self.repo}/pulls/{pr_number}"]
        )
        return json.loads(output)

    def get_comments(self, pr_number):
        output = self.gh_api(
            [f"repos/{self.owner}/{self.repo}/issues/{pr_number}/comments"]
        )
        return json.loads(output)

    def post_comment(self, pr_number, body):
        self.gh_api(
            [
                f"repos/{self.owner}/{self.repo}/issues/{pr_number}/comments",
                "-f", f"body={body}"
            ]
        )

    def update_comment(self, comment_id, body):
        self.gh_api(
            [
                f"repos/{self.owner}/{self.repo}/issues/comments/{comment_id}",
                "-X", "PATCH",
                "-f", f"body={body}"
            ]
        )

    def add_label(self, pr_number, label):
        self.gh_api(
            [
                f"repos/{self.owner}/{self.repo}/issues/{pr_number}/labels",
                "-f", f"labels[]={label}"
            ]
        )

    def get_labels(self, pr_number):
        output = self.gh_api(
            [f"repos/{self.owner}/{self.repo}/issues/{pr_number}/labels"]
        )
        return [l["name"] for l in json.loads(output)]

    # -----------------------------
    # Review Logic
    # -----------------------------

    def review_diff(self, diff):
        prompt = inject(load_agent_skill("pr-review"), {"diff": diff})
        output = run_claude(prompt, cwd=self.repo_path)
        return extract_json(output)

    # -----------------------------
    # Formatting
    # -----------------------------

    def format_review_comment(self, review):
        lines = []
        lines.append("## 🤖 AI PR Review\n")
        lines.append(f"**Status:** `{review['status']}`\n")
        lines.append(f"**Summary:** {review['summary']}\n")

        if review["issues"]:
            lines.append("### Issues:")
            for i, issue in enumerate(review["issues"], 1):
                lines.append(
                    f"{i}. [{issue['severity'].upper()}] {issue['message']}"
                )
        else:
            lines.append("✅ No major issues found")

        return "\n".join(lines)

    # -----------------------------
    # Review Flow
    # -----------------------------

    def run_review(self, pr_number):
        print(f"\n🔍 Running AI review for PR #{pr_number}...\n")

        diff = self.get_pr_diff(pr_number)
        review = self.review_diff(diff)
        body = self.format_review_comment(review)

        comments = self.get_comments(pr_number)

        existing = None
        for c in comments:
            if "## 🤖 AI PR Review" in c["body"]:
                existing = c
                break

        if existing:
            print("✏️ Updating existing AI review comment...")
            self.update_comment(existing["id"], body)
        else:
            print("💬 Posting new AI review comment...")
            self.post_comment(pr_number, body)

        if review["status"] == "pass":
            self.add_label(pr_number, "ai-review:passed")
        else:
            self.add_label(pr_number, "ai-review:needs-fix")

        return review

    # -----------------------------
    # Merge
    # -----------------------------

    def merge_pr(self, pr_number):
        print(f"\n🚀 Merging PR #{pr_number}...\n")

        self.gh_api(
            [
                f"repos/{self.owner}/{self.repo}/pulls/{pr_number}/merge",
                "-X", "PUT",
                "-f", "merge_method=squash"
            ]
        )

        print("✅ PR merged successfully")

    def approve_and_merge(self, pr_number):
        labels = self.get_labels(pr_number)

        if "ai-review:needs-fix" in labels:
            raise Exception("❌ Cannot merge: AI review requires changes")

        return self.merge_pr(pr_number)
    
    def force_merge(self, pr_number):
        print(f"\n🚀 Force merging PR #{pr_number} (override AI review)...\n")

        self.gh_api(
            [
                f"repos/{self.owner}/{self.repo}/pulls/{pr_number}/merge",
                "-X", "PUT",
                "-f", "merge_method=squash"
            ]
        )

        print("✅ PR force-merged successfully")