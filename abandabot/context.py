import os
import stat
import json
import shutil
import logging
import subprocess
import pandas as pd

from typing import Optional
from collections import defaultdict

from abandabot import REPO_PATH, CODEQL_DB_PATH, REPORT_PATH
from abandabot.codeql import create_database, execute_query


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


def find_keyword_usage(repo: str, overwrite: bool) -> Optional[pd.DataFrame]:
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    df_path = os.path.join(report_path, "keyword-usage.csv")
    os.makedirs(report_path, exist_ok=True)

    if not overwrite and os.path.exists(df_path):
        logging.info("Keyword usage found at %s", df_path)
        return pd.read_csv(df_path)

    encoding = {"encoding": "utf-8", "errors": "ignore"}

    keyword_usage = defaultdict(set)

    if not os.path.exists(os.path.join(repo_path, "package.json")):
        logging.info("Skipping keyword usage creation, no package.json found")
        logging.info("Currently only JS/TS projects using npm are supported")
        return None

    with open(os.path.join(repo_path, "package.json"), "r", **encoding) as f:
        package_json = json.load(f)
    all_deps = set(package_json.get("dependencies", {}).keys()) | set(
        package_json.get("devDependencies", {}).keys()
    )

    for root, _, files in os.walk(repo_path):
        for file in files:
            # Skip lock files, symlinks, and files larger than 10kb
            if file.endswith(("package-lock.json")):
                continue
            if os.path.islink(os.path.join(root, file)):
                continue
            if os.path.getsize(os.path.join(root, file)) > 10 * 1024:
                continue

            full_path = os.path.relpath(os.path.join(root, file), repo_path)

            if full_path.startswith(".git") or full_path.startswith("node_modules"):
                continue

            with open(os.path.join(root, file), "r", **encoding) as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                for dep in all_deps:
                    if dep in line:
                        keyword_usage[dep].add((full_path, i + 1))

    keyword_usage_df = []
    for dep, values in keyword_usage.items():
        for file, lineno in values:
            keyword_usage_df.append({"name": dep, "file": file, "lineno": lineno})
    keyword_usage_df = pd.DataFrame(keyword_usage_df)
    keyword_usage_df.to_csv(df_path, index=False)
    return keyword_usage_df


def find_dep_usage_codeql(repo: str, overwrite: bool) -> Optional[pd.DataFrame]:
    clone_repo(repo, overwrite=overwrite)

    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    database_path = os.path.join(CODEQL_DB_PATH, repo.replace("/", "_"))
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    dep_usage_path = os.path.join(report_path, "dep-usage.csv")
    if os.path.exists(dep_usage_path) and not overwrite:
        logging.info("Dep usage found at %s", dep_usage_path)
        return pd.read_csv(dep_usage_path)

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

    return pd.read_csv(dep_usage_path)


def find_api_usage_codeql(repo: str, overwrite: bool) -> Optional[pd.DataFrame]:
    clone_repo(repo, overwrite=overwrite)

    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    database_path = os.path.join(CODEQL_DB_PATH, repo.replace("/", "_"))
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    api_usage_path = os.path.join(report_path, "api-usage.csv")
    if os.path.exists(api_usage_path) and not overwrite:
        logging.info("API usage found at %s", api_usage_path)
        return pd.read_csv(api_usage_path)

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
        query_path="queries/find_api_usage.ql",
        database_path=database_path,
        output_path=os.path.join(report_path, "api-usage.bqrs"),
        decode_path=os.path.join(report_path, "api-usage.csv"),
    )

    return pd.read_csv(api_usage_path)


def build_dep_context(repo: str, dep: str, overwrite: bool) -> dict[str, set[int]]:
    context = defaultdict(set)

    for kind, usage in [
        ("keyword", find_keyword_usage(repo, overwrite)),
        ("import", find_dep_usage_codeql(repo, overwrite)),
        ("api", find_api_usage_codeql(repo, overwrite)),
    ]:
        if usage is None or dep not in set(usage.name):
            logging.warning(
                "Dep %s %s usage not found in %s, found are: %s",
                dep,
                kind,
                repo,
                set(usage.name),
            )
        else:
            # if a lot of usages are detected, many of them may be suprious
            # To avoid exceeding the token limit, we randomly sample 50 usages
            usage = usage[usage["name"] == dep]
            if len(usage) > 50:
                logging.info("Sampling 50 out of %d usages from %s", len(usage), kind)
                usage = usage.sample(n=min(50, len(usage)))
            for _, row in usage.iterrows():
                context[row["file"]].add(row["lineno"])

    return context
