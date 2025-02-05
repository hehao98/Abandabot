import os
import sys
import stat
import json
import shutil
import logging
import argparse
import subprocess
import dotenv
import pandas as pd

from langchain_openai import ChatOpenAI

from abandabot import REPO_PATH, CODEQL_DB_PATH, REPORT_PATH
from abandabot.codeql import install_codeql_cli, create_database, execute_query
from abandabot.prompt import AbandabotReport, build_abandabot_prompt


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
        ["git", "clone", f"https://github.com/{repo}.git", repo_path],
        check=True,
        stdout=subprocess.PIPE,
    )


def find_dep_usage_codeql(repo: str, overwrite: bool) -> pd.DataFrame:
    clone_repo(repo, overwrite=overwrite)

    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    database_path = os.path.join(CODEQL_DB_PATH, repo.replace("/", "_"))
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    os.makedirs(report_path, exist_ok=True)

    if not os.path.exists(os.path.join(repo_path, "package.json")):
        logging.info("Skipping CodeQL database creation, no package.json found")
        logging.info("Currently only JS/TS projects using npm are supported")
        return

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


def generate_report(repo: str, dep: str, dep_usage: pd.DataFrame) -> None:
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    prompt_path = os.path.join(report_path, f"prompt-{dep}.txt")
    output_path = os.path.join(report_path, f"report-{dep}.json")

    model_name = "gpt-4o-mini"
    model = ChatOpenAI(model=model_name).with_structured_output(AbandabotReport)

    logging.info("Generating report for %s using %s", repo, model_name)
    prompt = build_abandabot_prompt(repo, dep, dep_usage)
    with open(prompt_path, "w") as f:
        f.write(prompt)
    logging.info("Prompt saved to %s", prompt_path)

    output = model.invoke(prompt)
    with open(output_path, "w") as f:
        f.write(json.dumps(output, indent=2))
    logging.info("Report saved to %s", output_path)


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    check_env()

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

    logging.info("GitHub repository: %s", args.github)

    dep_usage = find_dep_usage_codeql(args.github, args.overwrite)
    if args.dep not in set(dep_usage.name):
        logging.info(
            "Dependency %s not found in %s, found deps are: ",
            args.dep,
            args.github,
            set(dep_usage.name),
        )
        return

    generate_report(args.github, args.dep, dep_usage)
    logging.info("Report generated successfully")


if __name__ == "__main__":
    main()
