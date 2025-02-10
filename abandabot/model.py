import os
import json
import logging

from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from abandabot import REPO_PATH, CODEQL_DB_PATH, REPORT_PATH


PROMPT_BASE = """
You are an expert JavaScript developer. I am going to ask you important dependency 
management questions regarding whether I will need to take action if a dependency gets abandoned.
I will provide you with the project's README file, the project's package.json file, 
the dependency name, and partial code snippets from this project 
where the dependency is used. I want you to evaluate the following four dimensions 
regarding the dependency and the project:

1. How important is the functionality provided by the dependency to the project? 
2. How difficult is it to replace the dependency, considering the depth of its integration in the project’s code base?
3. How difficult is it to replace the dependency, considering the availability of alternative packages that could serve as suitable replacements and provide the same functionality?
4. How likely is it that external environmental changes will force the project to act on the dependency's abandonment?

For each question, I want you to provide an answer on a scale from 1 to 5, where 
1 is the least important, difficult, or likely, and 5 is the most important, 
difficult, or likely. Along with the score, please provide detailed, specific reasoning 
behind the score. Finally, please provide a final score from one of 
the following options:

1. Immediate action is necessary
2. Action is advisable
3. No immediate action is necessary

You should also provide detailed, specific reasoning for your final recommendation.

The dependency I want to ask is {dep}. I provide relevant files as follows:

[start of README.md]
{readme}
[end of README.md]

[start of package.json]
{pkg_json}
[end of package.json]
"""


class AbandabotReport(TypedDict):
    class Dimension(TypedDict):
        score: int
        reasoning: str

    class Recommendation(TypedDict):
        score: str
        reasoning: str

    importance: Dimension
    integration: Dimension
    alternatives: Dimension
    likelihood: Dimension
    recommendation: Recommendation


def build_abandabot_prompt(
    repo: str, dep: str, context: dict[str, set[int]], context_window: int = 10
) -> str:
    """Build a prompt for Abandabot

    Args:
        repo (str): The repository name
        dep (str): The dependency name
        context (dict[str, set[int]]): A dictionary of file names
            and line numbers where the dependency is used
        context_window (int, optional): The number of lines to include
            per dependency usage. Defaults to 10.

    Returns:
        str: The prompt for Abandabot
    """
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    encoding = {"encoding": "utf-8", "errors": "ignore"}

    if os.path.exists(os.path.join(repo_path, "README.md")):
        with open(os.path.join(repo_path, "README.md"), "r", **encoding) as f:
            readme = f.read()
        # only keep the first 15 lines of the README
        readme = "\n".join(readme.split("\n")[:15]) + "\n...\n"
    else:
        readme = "NOT FOUND"

    with open(os.path.join(repo_path, "package.json"), "r", **encoding) as f:
        pkg_json = f.read()

    prompt = PROMPT_BASE.format(dep=dep, readme=readme, pkg_json=pkg_json)

    for file, linenos in context:
        with open(os.path.join(repo_path, file), "r", **encoding) as f:
            code_lines = f.read().split("\n")

        all_lines_in_context = set()
        for lineno in sorted(linenos):
            start = max(0, lineno - context_window)
            end = min(len(code_lines), lineno + context_window)
            all_lines_in_context.update(range(start, end))

        code = ""
        for lineno in range(len(code_lines)):
            if lineno in all_lines_in_context:
                code += str(lineno) + " " + code_lines[lineno] + "\n"
            elif (lineno - 1) in all_lines_in_context:
                code += "...\n"

        prompt += f"\n[start of {file}]\n{code}\n[end of {file}]\n"

    return prompt


def generate_report(repo: str, dep: str, context: dict[str, set[int]]) -> None:
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    prompt_path = os.path.join(report_path, f"prompt-{dep.replace('/', '_')}.txt")
    output_path = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")

    model_name = "gpt-4o-mini"
    model = ChatOpenAI(model=model_name).with_structured_output(AbandabotReport)

    logging.info("Generating report for %s using %s", repo, model_name)
    prompt = build_abandabot_prompt(repo, dep, context)
    with open(prompt_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(prompt)
    logging.info("Prompt saved to %s", prompt_path)

    output = model.invoke(prompt)
    with open(output_path, "w") as f:
        f.write(json.dumps(output, indent=2))
    logging.info("Report saved to %s", output_path)
