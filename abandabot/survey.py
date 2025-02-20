import os
import json
import random
import dotenv
import logging
import pymongo
import subprocess
import pandas as pd
import multiprocessing as mp

from typing import Optional
from github import Github
from apiclient import discovery
from httplib2 import Http
from oauth2client import client, file, tools

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

    if len(all_deps) >= 20:
        logging.info("Too many dependencies, sampling 20")
        all_deps = random.sample(all_deps, 20)

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
                    "--summarize",
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
    # create a banket survey for the repo in Google Form
    SCOPES = "https://www.googleapis.com/auth/forms.body"
    DISCOVERY_DOC = "https://forms.googleapis.com/$discovery/rest?version=v1"

    store = file.Storage("token.json")
    creds = None
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets("credentials.json", SCOPES)
        creds = tools.run_flow(flow, store)

    form_service = discovery.build(
        "forms",
        "v1",
        http=creds.authorize(Http()),
        discoveryServiceUrl=DISCOVERY_DOC,
        static_discovery=False,
    )

    # Request body for creating a form
    NEW_FORM = {
        "info": {
            "title": "Quickstart form",
        }
    }

    # Request body to add a multiple-choice question
    NEW_QUESTION = {
        "requests": [
            {
                "createItem": {
                    "item": {
                        "title": (
                            "In what year did the United States land a mission on"
                            " the moon?"
                        ),
                        "questionItem": {
                            "question": {
                                "required": True,
                                "choiceQuestion": {
                                    "type": "RADIO",
                                    "options": [
                                        {"value": "1965"},
                                        {"value": "1967"},
                                        {"value": "1969"},
                                        {"value": "1971"},
                                    ],
                                    "shuffle": True,
                                },
                            }
                        },
                    },
                    "location": {"index": 0},
                }
            }
        ]
    }

    # Creates the initial form
    result = form_service.forms().create(body=NEW_FORM).execute()

    # Adds the question to the form
    question_setting = (
        form_service.forms()
        .batchUpdate(formId=result["formId"], body=NEW_QUESTION)
        .execute()
    )

    # Prints the result to show the question has been added
    get_result = form_service.forms().get(formId=result["formId"]).execute()
    print(get_result)


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )

    logging.info("Start!")

    random.seed(114514)

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
    sample_repos = sorted(candidates.repoSlug.sample(2000, random_state=114514))

    #with mp.Pool(8) as pool:
    #    pool.starmap(collect_reports, [(repo, "deepseek-v3") for repo in sample_repos])

    for repo in sample_repos:
        collect_reports(repo, model="deepseek-v3")

    # generate_surveys(repo)

    logging.info("Done!")


if __name__ == "__main__":
    main()
