import os
import sys
import logging
import subprocess


from abandabot import CODEQL_PATH, CODEQL_CLI_PATH


def check_codeql_cli() -> None:
    if not os.path.exists(CODEQL_PATH):
        raise ValueError("CodeQL CLI is not installed")

    subprocess.run(
        [CODEQL_CLI_PATH, "resolve", "packs"],
        check=True,
        stdout=subprocess.PIPE,
    )
    logging.info("CodeQL CLI is installed and working correctly")


def install_codeql_cli() -> None:
    if sys.maxsize <= 2**32:
        raise ValueError("CodeQL cli does not support 32-bit systems")

    if os.path.exists(CODEQL_PATH):
        check_codeql_cli()
        return

    if sys.platform.startswith("win"):
        os_name = "win64"
    elif sys.platform.startswith("darwin"):
        os_name = "osx64"
    else:
        os_name = "linux64"

    url = (
        "https://github.com/github/codeql-action/releases/download/"
        + f"codeql-bundle-v2.20.4/codeql-bundle-{os_name}.tar.gz"
    )
    logging.info(f"Downloading CodeQL CLI from {url}")
    subprocess.run(
        ["curl", "-L", url, "--output", "codeql.tar.gz"],
        check=True,
        stdout=subprocess.PIPE,
    )

    logging.info("Extracting CodeQL CLI")
    subprocess.run(["tar", "-xzf", "codeql.tar.gz"], check=True, stdout=subprocess.PIPE)

    logging.info("Cleaning up CodeQL CLI")
    os.remove("codeql.tar.gz")

    check_codeql_cli()
    logging.info("CodeQL CLI installed successfully")


def create_database(
    repo_path: str,
    database_path: str,
    language: str,
    overwrite: bool = False,
) -> None:
    if not overwrite and os.path.exists(database_path):
        logging.info("CodeQL database already exists at %s", database_path)
        return

    logging.info("Creating CodeQL database at %s for repo %s", database_path, repo_path)
    subprocess.run(
        [
            CODEQL_CLI_PATH,
            "database",
            "create",
            database_path,
            "--source-root",
            repo_path,
            f"--language={language}",
            "--overwrite",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )


def execute_query(query_path: str, database_path: str, output_path: str) -> None:
    logging.info("Executing CodeQL query %s on database %s", query_path, database_path)
    subprocess.run(
        [
            CODEQL_CLI_PATH,
            "database",
            "analyze",
            database_path,
            query_path,
            "--format=csv",
            f"--output={output_path}",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    logging.info("CodeQL query results saved to %s", output_path)
