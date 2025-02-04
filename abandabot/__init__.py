# read pyproject.toml
import tomllib

with open("pyproject.toml", "rb") as f:
    PY_PROJECT = tomllib.load(f)

CODEQL_PATH = PY_PROJECT["tool"]["abandabot"]["codeql-path"]
CODEQL_CLI_PATH = PY_PROJECT["tool"]["abandabot"]["codeql-cli-path"]
CODEQL_DB_PATH = PY_PROJECT["tool"]["abandabot"]["codeql-db-path"]

REPO_PATH = PY_PROJECT["tool"]["abandabot"]["repo-path"]
REPORT_PATH = PY_PROJECT["tool"]["abandabot"]["report-path"]