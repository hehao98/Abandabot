import os
import sys
import stat
import shutil
import logging
import argparse
import subprocess


from abandabot import REPO_PATH, CODEQL_DB_PATH, REPORT_PATH
from abandabot.codeql import install_codeql_cli, create_database, execute_query


def remove_readonly(func, path, _):
    "Clear the readonly bit and reattempt the removal"
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clone_repo(repo_name: str, overwrite: bool = False) -> None:
    os.makedirs(REPO_PATH, exist_ok=True)

    repo_path = os.path.join(REPO_PATH, repo_name.replace("/", "_"))

    if os.path.exists(repo_path):
        if overwrite:
            logging.info("Overwriting existing repository at %s", repo_path)
            shutil.rmtree(repo_path, onexc=remove_readonly)
        else:
            logging.info("Repository already cloned to %s, skipping", repo_path)
            return

    logging.info(f"Cloning repository {repo_name}")
    subprocess.run(
        ["git", "clone", f"https://github.com/{repo_name}.git", repo_path],
        check=True,
        stdout=subprocess.PIPE,
    )


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    install_codeql_cli()
    os.makedirs(CODEQL_DB_PATH, exist_ok=True)
    os.makedirs(REPO_PATH, exist_ok=True)
    os.makedirs(REPORT_PATH, exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--github",
        type=str,
        required=True,
        help="GitHub repository in the format 'owner/repo'",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the GitHub repository and CodeQL DB if it already exists",
    )
    args = parser.parse_args()

    logging.info(f"GitHub repository: {args.github}")

    clone_repo(args.github, overwrite=args.overwrite)

    repo_path = os.path.join(REPO_PATH, args.github.replace("/", "_"))
    database_path = os.path.join(CODEQL_DB_PATH, args.github.replace("/", "_"))
    report_path = os.path.join(REPORT_PATH, f"{args.github.replace('/', '_')}")
    os.makedirs(report_path, exist_ok=True)

    if not os.path.exists(os.path.join(repo_path, "package.json")):
        logging.info("Skipping CodeQL database creation, no package.json found")
        logging.info("Currently only JS/TS projects using npm are supported")
        return

    create_database(
        repo_path,
        database_path,
        language="javascript",
        overwrite=args.overwrite,
    )

    execute_query(
        query_path="queries/find_dep_usage.ql",
        database_path=database_path,
        output_path=os.path.join(report_path, "dep-usage.csv"),
    )


if __name__ == "__main__":
    main()
