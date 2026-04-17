import subprocess
import os
import glob


def deploy_to_test(state, REPO_PATH, CONFIG):
    print("\n=== STEP: DEPLOY_TO_TEST ===\n")

    # -----------------------------
    # Only deploy if PR merged
    # -----------------------------
    if not state.get("merged"):
        print("⏭ Skipping deploy (PR not merged)")
        return "release_notes"

    print("🚀 PR merged — deploying develop branch...\n")

    # -----------------------------
    # Sync repo to develop
    # -----------------------------
    print("🔄 Syncing local repo with origin/develop...")

    subprocess.run(["git", "fetch", "origin"], cwd=REPO_PATH, check=True)
    subprocess.run(["git", "reset", "--hard"], cwd=REPO_PATH, check=True)
    subprocess.run(["git", "checkout", "develop"], cwd=REPO_PATH, check=True)
    subprocess.run(["git", "pull", "origin", "develop"], cwd=REPO_PATH, check=True)

    commit_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_PATH,
        text=True
    ).strip()

    print(f"📌 Deploying commit: {commit_sha}")

    # -----------------------------
    # Build JAR
    # -----------------------------
    print("\n🔨 Building JAR...")
    subprocess.run(
        ["./mvnw", "clean", "package", "spring-boot:repackage", "-DskipTests"],
        cwd=REPO_PATH,
        check=True
    )

    # -----------------------------
    # Locate JAR
    # -----------------------------
    jar_files = glob.glob(f"{REPO_PATH}/target/*.jar")
    jar_files = [f for f in jar_files if "original" not in f]

    if not jar_files:
        raise Exception("No JAR found in target/")

    LOCAL_JAR = jar_files[0]
    JAR_NAME = os.path.basename(LOCAL_JAR)

    # -----------------------------
    # Config
    # -----------------------------
    KEY_PATH = os.path.expanduser(CONFIG["deploy_key"])
    EC2_HOST = CONFIG["deploy_host"]
    EC2_USER = CONFIG["deploy_user"]

    BASE_DIR = "/home/ec2-user/unicorn"
    RELEASES_DIR = f"{BASE_DIR}/releases"
    REMOTE_JAR = f"{RELEASES_DIR}/{JAR_NAME}"
    SYMLINK_PATH = f"{BASE_DIR}/unicorn-app.jar"

    # -----------------------------
    # Upload JAR
    # -----------------------------
    print("📦 Uploading JAR to EC2...")

    subprocess.run(
        [
            "scp",
            "-i", KEY_PATH,
            "-o", "StrictHostKeyChecking=no",
            LOCAL_JAR,
            f"{EC2_USER}@{EC2_HOST}:{REMOTE_JAR}"
        ],
        check=True
    )

    # -----------------------------
    # Remote deploy
    # -----------------------------
    print("🚀 Deploying on EC2...")

    remote_cmd = f"""
    set -e

    echo "Stopping service..."
    sudo systemctl stop fractal-ai || true

    echo "Updating symlink..."
    ln -sfn {REMOTE_JAR} {SYMLINK_PATH}

    echo "Starting service..."
    sudo systemctl start fractal-ai

    echo "Waiting for service to become healthy..."

    healthy=false

    for i in {{1..20}}; do
    if curl -sf http://localhost:8080/actuator/health > /dev/null; then
        echo "✅ Service is healthy"
        healthy=true
        break
    fi

    echo "⏳ Attempt $i: not ready yet..."
    sleep 3
    done

    if [ "$healthy" != true ]; then
    echo "❌ Service failed to become healthy"
    sudo systemctl status fractal-ai --no-pager || true
    exit 1
    fi

    echo "✅ Deployment successful"
    """

    subprocess.run(
        [
            "ssh",
            "-i", KEY_PATH,
            "-o", "StrictHostKeyChecking=no",
            f"{EC2_USER}@{EC2_HOST}",
            remote_cmd
        ],
        check=True
    )

    print("\n🎉 Deploy complete\n")

    return "release_notes"