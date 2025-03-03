import os
import json
import gzip
import base64
import random
import dotenv
import logging
import pymongo
import argparse
import subprocess
import pandas as pd
import multiprocessing as mp

from typing import Optional
from collections import defaultdict, Counter
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


def generate_reports(repo: str, model: str) -> None:
    pkg_json = get_repo_pkg_json(repo)
    all_deps = list(pkg_json.get("dependencies", {}).keys()) + list(
        pkg_json.get("devDependencies", {}).keys()
    )

    logging.info("repo %s: %s", repo, all_deps)

    if len(all_deps) >= 10:
        logging.info("Too many dependencies, sampling 10")
        all_deps = random.sample(all_deps, 10)

    for dep in all_deps:
        with pymongo.MongoClient(MONGO_URI) as client:
            collection = client.abandabot.survey_reports
            query = {"repo": repo, "model": model}
            if collection.count_documents(query) >= 10:
                logging.info("Reports from %s %s already suffice", repo, model)
                break
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
                # stdout=subprocess.PIPE,
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


def collect_surveys() -> None:
    with pymongo.MongoClient(MONGO_URI) as client:
        all_repos = list(client.abandabot.survey_reports.distinct("repo"))
        reports = list(client.abandabot.survey_reports.find())

    dep_counter = defaultdict(Counter)
    for report in reports:
        dep_counter[report["dep"]][report["report"]["impactful"]] += 1
    context_deps = {
        dep
        for dep, counter in dep_counter.items()
        if len(counter) > 1 and counter[True] >= 1 and counter[False] >= 1
    }
    logging.info("%d deps with context_specifc judgements", len(context_deps))

    if os.path.exists("survey_candidates.json"):
        with open("survey_candidates.json", "r") as f:
            survey_candidates = json.load(f)
        logging.info(
            "%d candidates loaded from previous survey_candidates.json",
            len(survey_candidates),
        )
    else:
        survey_candidates = []

    remaining = set(all_repos) - {c["repo"] for c in survey_candidates}
    logging.info("%d repos left to collect", len(remaining))
    for repo in remaining:
        with pymongo.MongoClient(MONGO_URI) as client:
            reports = list(client.abandabot.survey_reports.find({"repo": repo}))

        all_deps = {r["dep"] for r in reports}
        impacful_deps = {r["dep"] for r in reports if r["report"]["impactful"]}
        non_impactful_deps = all_deps - impacful_deps
        logging.info(
            "%s: %d deps, %d impactful, %d non-impactful, %d context-specific",
            repo,
            len(all_deps),
            len(impacful_deps),
            len(non_impactful_deps),
            len(context_deps & all_deps),
        )
        if (
            len(context_deps & all_deps) >= 3
            and len(impacful_deps) > 0
            and len(non_impactful_deps) > 0
        ):
            dep1 = random.choice(list(impacful_deps))
            dep2 = random.choice(list(non_impactful_deps))
            dep3 = random.choice(list((context_deps & all_deps) - {dep1, dep2}))
            survey_candidates.append(
                {
                    "repo": repo,
                    "dep1": dep1,
                    "dep2": dep2,
                    "dep3": dep3,
                    "dep1_report": next(
                        r["report"] for r in reports if r["dep"] == dep1
                    ),
                    "dep2_report": next(
                        r["report"] for r in reports if r["dep"] == dep2
                    ),
                    "dep3_report": next(
                        r["report"] for r in reports if r["dep"] == dep3
                    ),
                }
            )
            del survey_candidates[-1]["dep1_report"]["summary"]
            del survey_candidates[-1]["dep2_report"]["summary"]
            del survey_candidates[-1]["dep3_report"]["summary"]

    with open("survey_candidates.json", "w") as f:
        json.dump(survey_candidates, f, indent=2)

    json_data = json.dumps(survey_candidates, indent=2)
    compressed_data = base64.b64encode(gzip.compress(json_data.encode())).decode()
    with open("survey_candidates_compressed.txt", "w") as f:
        f.write(compressed_data)

    logging.info(
        "%d candidates from %d repos saved",
        len(survey_candidates),
        len(all_repos),
    )


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )

    logging.info("Start!")

    random.seed(11451419)

    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()

    if args.run:
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
        sample_repos = sorted(candidates.repoSlug.sample(2000))

        with mp.Pool(4) as pool:
            pool.starmap(
                generate_reports, [(repo, "deepseek-v3") for repo in sample_repos]
            )
    elif args.collect:
        collect_surveys()

    logging.info("Done!")


if __name__ == "__main__":
    main()
