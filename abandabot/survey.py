import os
import json
import dotenv
import logging
import pymongo
import subprocess
import pandas as pd

from typing import Optional
from github import Github
from abandabot import REPORT_PATH, MONGO_URI


def get_repo_pkg_json(repo: str) -> Optional[dict]:
    dotenv.load_dotenv()
    github = Github(os.getenv("GITHUB_TOKEN"))
    try:
        content = github.get_repo(repo).get_contents("package.json")
        return json.loads(content.decoded_content)
    except Exception as ex:
        logging.error("Cannot access package.json in %s, %s", repo, ex)
        return None


def collect_reports(repo: str, model: str) -> None:
    pkg_json = get_repo_pkg_json(repo)
    all_deps = list(pkg_json.get("dependencies", {}).keys()) + list(
        pkg_json.get("devDependencies", {}).keys()
    )

    logging.info("repo %s: %s", repo, all_deps)

    for dep in all_deps:
        with pymongo.MongoClient(MONGO_URI) as client:
            collection = client.abandabot.survey_reports
            query = {"repo": repo, "dep": dep, "model": model}
            if collection.count_documents(query) > 0:
                logging.info("Report %s %s %s already exist", repo, dep, model)
                continue

        try:
            subprocess.run(
                [
                    "poetry",
                    "run",
                    "python",
                    "-m",
                    "abandabot",
                    "--github",
                    repo,
                    "--dep",
                    dep,
                    "--model",
                    model,
                    "--include-reasoning",
                    "--include-context",
                    "--complex-reasoning",
                ],
                check=True,
                stdout=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            logging.error("Error: %s", e)
            continue

        path = os.path.join(REPORT_PATH, repo.replace("/", "_"))
        file = os.path.join(path, f"report-{dep.replace('/', '_')}.json")
        with open(file, "r") as f:
            report: dict = json.load(f)
        with pymongo.MongoClient(MONGO_URI) as client:
            collection = client.abandabot.survey_reports
            collection.insert_one(
                {"repo": repo, "dep": dep, "model": model, "report": report}
            )
        logging.info("%s %s -> %s", repo, dep, report)

    return


def generate_surveys(repo: str) -> None:
    pass


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )

    logging.info("Start!")

    with pymongo.MongoClient(MONGO_URI) as client:
        client.abandabot.survey_reports.create_index(
            [
                ("repo", 1),
                ("dep", 1),
                ("model", 1),
            ],
            unique=True,
        )

    candidates = pd.read_csv("survey_repos.csv")
    sample_repos = sorted(candidates.repoSlug.sample(1000, random_state=114514))
    sample_repos = sample_repos[:10]  # test on 10 repos first

    for repo in sample_repos:
        collect_reports(repo, model="gpt-4o-mini")

        collect_reports(repo, model="deepseek-v3")

        generate_surveys(repo)

    logging.info("Done!")
