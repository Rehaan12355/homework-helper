"""Builds Homework Helper for AWS Lambda and deploys template.yaml.

Uses only the AWS CLI (no SAM CLI needed): `aws cloudformation package`
uploads the code to S3, then `aws cloudformation deploy` creates the stack.
Settings come from .env. If MCP_API_KEY isn't set, one is made and saved
there.

  python deploy/deploy.py            build and deploy
  python deploy/deploy.py --build    only build build/lambda.zip
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
STACK = os.environ.get("STACK_NAME", "homework-helper")


def build() -> Path:
    """Installs Linux packages for Lambda's Python and zips them with the code."""
    site = BUILD / "lambda"
    shutil.rmtree(site, ignore_errors=True)
    # uv, not pip: pip judges markers like `sys_platform == "win32"` by the
    # computer it runs on, so on Windows it tries to install pywin32 for Linux.
    if not shutil.which("uv"):
        sys.exit("Building for Lambda needs uv: pip install uv")
    subprocess.run(["uv", "pip", "install", "--quiet",
                    "--python-platform", "x86_64-manylinux2014", "--python-version", "3.13",
                    "--only-binary", ":all:", "--target", str(site),
                    "-r", str(ROOT / "deploy" / "requirements-lambda.txt")],
                   check=True)
    shutil.copytree(ROOT / "homework_helper", site / "homework_helper",
                    ignore=shutil.ignore_patterns("__pycache__"))

    out = BUILD / "lambda.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(site.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                info = zipfile.ZipInfo(path.relative_to(site).as_posix(), (2020, 1, 1, 0, 0, 0))
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, path.read_bytes())
        # Zips made on Windows lose the executable bit, and git may have
        # given the script Windows line endings; Lambda needs neither.
        info = zipfile.ZipInfo("run.sh", (2020, 1, 1, 0, 0, 0))
        info.external_attr = 0o755 << 16
        z.writestr(info, (ROOT / "deploy" / "run.sh").read_bytes().replace(b"\r\n", b"\n"))
    print(f"Built {out.relative_to(ROOT)} ({out.stat().st_size // 1_000_000} MB)")
    return out


def aws(*args: str, capture: bool = False) -> str:
    result = subprocess.run(["aws", *args], check=True, text=True,
                            capture_output=capture)
    return result.stdout.strip() if capture else ""


def api_key() -> str:
    key = os.environ.get("MCP_API_KEY")
    if not key:
        key = secrets.token_urlsafe(32)
        with open(ROOT / ".env", "a") as f:
            f.write(f"\n# Bearer token for the cloud MCP server (made by deploy.py)\nMCP_API_KEY={key}\n")
        print("Made a new MCP_API_KEY and saved it in .env")
    return key


def deploy() -> None:
    load_dotenv(ROOT / ".env")
    for name in ("CANVAS_URL", "CANVAS_TOKEN"):
        if not os.environ.get(name):
            sys.exit(f"Set {name} in .env first.")
    build()

    account = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text", capture=True)
    region = aws("configure", "get", "region", capture=True) or "us-west-2"
    bucket = f"homework-helper-deploy-{account}-{region}"
    try:
        aws("s3api", "head-bucket", "--bucket", bucket, capture=True)
    except subprocess.CalledProcessError:
        aws("s3", "mb", f"s3://{bucket}", "--region", region)

    packaged = BUILD / "packaged.yaml"
    aws("cloudformation", "package", "--template-file", str(ROOT / "template.yaml"),
        "--s3-bucket", bucket, "--output-template-file", str(packaged))

    google_token = ROOT / os.environ.get("GOOGLE_TOKEN", "token.json")
    params = {
        "CanvasUrl": os.environ["CANVAS_URL"],
        "CanvasToken": os.environ["CANVAS_TOKEN"],
        "McpApiKey": api_key(),
        "StudentTimezone": os.environ.get("STUDENT_TIMEZONE") or "America/Los_Angeles",
        "StudyStart": os.environ.get("STUDY_START") or "16:00",
        "GoogleTokenJson": google_token.read_text() if google_token.exists() else "",
    }
    # Parameters go through a file so secrets stay off the command line.
    params_file = BUILD / "parameters.json"
    params_file.write_text(json.dumps([f"{k}={v}" for k, v in params.items()]))
    try:
        aws("cloudformation", "deploy", "--template-file", str(packaged),
            "--stack-name", STACK, "--region", region,
            "--capabilities", "CAPABILITY_IAM", "CAPABILITY_AUTO_EXPAND",
            "--parameter-overrides", f"file://{params_file}")
    finally:
        params_file.unlink()

    outputs = json.loads(aws("cloudformation", "describe-stacks", "--stack-name", STACK,
                             "--region", region, "--query", "Stacks[0].Outputs",
                             "--output", "json", capture=True))
    print("\nDeployed. Add these to .env to use the cloud from the Alexa+ app:")
    for o in outputs:
        name = {"McpUrl": "MCP_URL", "HomeworkTableName": "HOMEWORK_TABLE"}[o["OutputKey"]]
        print(f"  {name}={o['OutputValue']}")


if __name__ == "__main__":
    build() if "--build" in sys.argv else deploy()
