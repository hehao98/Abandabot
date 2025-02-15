import os
import sys
import shutil
import logging
import argparse
import dotenv

from abandabot import REPO_PATH, CODEQL_DB_PATH, REPORT_PATH
from abandabot.codeql import install_codeql_cli
from abandabot.model import generate_report
from abandabot.context import build_dep_context


def check_env(model: str) -> None:
    dotenv.load_dotenv()

    if not shutil.which("git"):
        raise RuntimeError("git is not installed")

    required_env_vars = []
    if model == "chatgpt-4o-mini":
        required_env_vars.append("OPENAI_API_KEY")
    elif model in ("deepseek-v3", "llama-v3p1", "llama-v3p3"):
        required_env_vars.append("FIREWORKS_API_KEY")
    elif model == "claude-3-5":
        required_env_vars.append("ANTHROPIC_API_KEY")

    for var in required_env_vars:
        if var not in os.environ:
            raise RuntimeError(f"{var} is not set in the local .env file")


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--github",
        type=str,
        required=True,
        help="GitHub repository in the format 'owner/repo'",
    )
    parser.add_argument(
        "--dep",
        type=str,
        required=True,
        help="The abandoned dependency to evaluate (e.g. 'lodash')",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        choices=["gpt-4o-mini", "deepseek-v3", "llama-v3p1", "llama-v3p3", "claude-3-5", "gemini-2.0"],
        help="The model to use for dependency evaluation",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the GitHub repository and CodeQL DB if it already exists",
    )
    parser.add_argument(
        "--exclude-reasoning",
        action="store_true",
        help="Exclude multiple dimensions of reasoning for dependency evaluation in the report",
    )
    parser.add_argument(
        "--exclude-context",
        action="store_true",
        help="Exclude project and dependency context information in the report",
    )

    args = parser.parse_args()

    check_env(args.model)

    install_codeql_cli()
    os.makedirs(CODEQL_DB_PATH, exist_ok=True)
    os.makedirs(REPO_PATH, exist_ok=True)
    os.makedirs(REPORT_PATH, exist_ok=True)

    logging.info("GitHub repository: %s", args.github)

    if not args.exclude_context:
        context = build_dep_context(args.github, args.overwrite)
    else:
        context = {}

    generate_report(
        args.github,
        args.dep,
        args.model,
        not args.exclude_reasoning,
        not args.exclude_context,
        context,
    )

    logging.info("Report generated successfully")


if __name__ == "__main__":
    main()
