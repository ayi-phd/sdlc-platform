from modules.ai_pr_reviewer import AiPrReviewer
import sys


def run_pr_review_stage(config, pr_number, repo_path=None):
    """
    AI review + human approval stage.
    Returns True if PR merged, False otherwise.
    """

    reviewer = AiPrReviewer(
        owner=config["repo_owner"],
        repo=config["repo_name"],
        repo_path=repo_path,
    )

    print("\n🔍 Running AI PR review...")

    review = reviewer.run_review(pr_number)

    # -----------------------------
    # PASS CASE
    # -----------------------------
    if review["status"] == "pass":
        print("✅ AI review passed")

        if config.get("auto_merge_on_pass"):
            reviewer.approve_and_merge(pr_number)
            return True

        user_input = input("Approve & merge PR? (y/n): ").strip().lower()

        if user_input == "y":
            reviewer.approve_and_merge(pr_number)
            return True

        return False

    # -----------------------------
    # NEEDS CHANGES
    # -----------------------------
    print("⚠️ AI review found issues")

    iteration = 0
    max_iterations = config.get("max_fix_iterations", 3)

    while iteration < max_iterations:
        iteration += 1

        action = input("\nChoose: [f]ix, [a]ccept, [s]kip, [q]uit: ").strip().lower()

        # -----------------------------
        # FIX
        # -----------------------------
        if action == "f":
            print(f"🛠 Fix iteration {iteration}/{max_iterations}")

            # 🔌 Hook for your fix pipeline
            # apply_fixes(review["issues"])

            input("Press Enter after fixes are pushed...")

            review = reviewer.run_review(pr_number)

            if review["status"] == "pass":
                print("✅ Issues resolved")

                confirm = input("Merge PR? (y/n): ").strip().lower()

                if confirm == "y":
                    reviewer.approve_and_merge(pr_number)
                    return True

                return False

        # -----------------------------
        # ACCEPT (merge anyway)
        # -----------------------------
        elif action == "a":
            print("\n⚠️ Accepting PR despite issues...\n")

            reviewer.force_merge(pr_number)
            return True

        # -----------------------------
        # SKIP (do not merge)
        # -----------------------------
        elif action == "s":
            print("\n⏭ Skipping PR (not merging)\n")
            return False

        # -----------------------------
        # QUIT (exit pipeline)
        # -----------------------------
        elif action == "q":
            print("\n🛑 Quitting pipeline...\n")
            sys.exit(1)

        # -----------------------------
        # INVALID INPUT
        # -----------------------------
        else:
            print("Invalid choice. Please select f, a, s, or q.")
            iteration -= 1  # don't count invalid input

    print("❌ Max fix iterations reached")
    return False