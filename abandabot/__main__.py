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


def check_env() -> None:
    dotenv.load_dotenv()

    if not shutil.which("git"):
        raise RuntimeError("git is not installed")

    required_env_vars = ["OPENAI_API_KEY"]
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
        "--overwrite",
        action="store_true",
        help="Overwrite the GitHub repository and CodeQL DB if it already exists",
    )
    args = parser.parse_args()

    check_env()

    install_codeql_cli()
    os.makedirs(CODEQL_DB_PATH, exist_ok=True)
    os.makedirs(REPO_PATH, exist_ok=True)
    os.makedirs(REPORT_PATH, exist_ok=True)

    logging.info("GitHub repository: %s", args.github)

    context = build_dep_context(args.github, args.dep, args.overwrite)

    generate_report(args.github, args.dep, context)

    logging.info("Report generated successfully")


if __name__ == "__main__":
    main()
