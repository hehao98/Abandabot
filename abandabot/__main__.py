import os
import sys
import stat
import shutil
import logging
import argparse
import subprocess
import dotenv
import pandas as pd

from typing import Optional
from collections import defaultdict

from abandabot import REPO_PATH, CODEQL_DB_PATH, REPORT_PATH
from abandabot.codeql import install_codeql_cli, create_database, execute_query
from abandabot.model import generate_report


def check_env() -> None:
    dotenv.load_dotenv()

    if not shutil.which("git"):
        raise RuntimeError("git is not installed")

    required_env_vars = ["OPENAI_API_KEY"]
    for var in required_env_vars:
        if var not in os.environ:
            raise RuntimeError(f"{var} is not set in the local .env file")


def remove_readonly(func, path, _):
    "Clear the readonly bit and reattempt the removal"
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clone_repo(repo: str, overwrite: bool = False) -> None:
    os.makedirs(REPO_PATH, exist_ok=True)

    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))

    if os.path.exists(repo_path):
        if overwrite:
            logging.info("Overwriting existing repository at %s", repo_path)
            shutil.rmtree(repo_path, onexc=remove_readonly)
        else:
            logging.info("Repository already cloned to %s, skipping", repo_path)
            return

    logging.info(f"Cloning repository {repo}")
    subprocess.run(
        ["git", "clone", f"https://github.com/{repo}.git", repo_path, "--depth", "1"],
        check=True,
        stdout=subprocess.PIPE,
    )


def find_keyword_usage(repo: str, dep: str) -> dict[str, set[int]]:
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    df_path = os.path.join(report_path, "keyword-usage.csv")
    os.makedirs(report_path, exist_ok=True)

    encoding = {"encoding": "utf-8", "errors": "ignore"}
    
    keyword_usage = defaultdict(set)

    for root, _, files in os.walk(repo_path):
        for file in files:
            full_path = os.path.relpath(os.path.join(root, file), repo_path)

            with open(os.path.join(root, file), "r", **encoding) as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                if dep in line:
                    keyword_usage[full_path].add(i + 1)

    keyword_usage_df = []
    for file, linenos in keyword_usage.items():
        for lineno in linenos:
            keyword_usage_df.append({"file": file, "lineno": lineno})
    pd.DataFrame(keyword_usage_df).to_csv(df_path, index=False)

    return keyword_usage


def find_dep_usage_codeql(repo: str, overwrite: bool) -> Optional[pd.DataFrame]:
    clone_repo(repo, overwrite=overwrite)

    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    database_path = os.path.join(CODEQL_DB_PATH, repo.replace("/", "_"))
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")

    if not os.path.exists(os.path.join(repo_path, "package.json")):
        logging.info("Skipping CodeQL database creation, no package.json found")
        logging.info("Currently only JS/TS projects using npm are supported")
        return None

    create_database(
        repo_path,
        database_path,
        language="javascript",
        overwrite=overwrite,
    )

    execute_query(
        query_path="queries/find_dep_usage.ql",
        database_path=database_path,
        output_path=os.path.join(report_path, "dep-usage.bqrs"),
        decode_path=os.path.join(report_path, "dep-usage.csv"),
    )

    return pd.read_csv(os.path.join(report_path, "dep-usage.csv"))


def find_api_usage_codeql(repo: str, overwrite: bool) -> Optional[pd.DataFrame]:
    pass


def build_dep_context(repo: str, dep: str, overwrite: bool) -> dict[str, set[int]]:
    context = defaultdict(set)

    keyword_usage = find_keyword_usage(repo, dep)
    for file, linenos in keyword_usage.items():
        context[file].update(linenos)

    dep_usage = find_dep_usage_codeql(repo, overwrite)
    if dep_usage is None or dep not in set(dep_usage.name):
        logging.warning(
            "Dependency %s not found in %s, found deps are: %s",
            dep,
            repo,
            set(dep_usage.name),
        )
    else:
        for _, row in dep_usage.iterrows():
            if row["name"] == dep:
                context[row["file"]].add(row["useLineno"])

    return context


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
