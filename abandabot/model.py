import os
import json
import logging

from pathlib import Path
from typing import Iterator
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from abandabot import REPO_PATH, REPORT_PATH


PROMPT_BASE = """
You are an expert JavaScript developer. I am going to ask you important dependency 
management questions regarding whether I will need to take action if a dependency 
gets abandoned. I will provide you with the project's README file, the dependency 
name, list of files where the dependency is used, and partial code snippets from 
this project where the dependency is used. I want you to evaluate the following four 
dimensions regarding the dependency and the project:

1. How important is the functionality provided by the dependency to the project? 
2. How difficult is it to replace the dependency, considering the depth of its 
    integration in the project’s code base?
3. How difficult is it to replace the dependency, considering the availability of 
    alternative packages that could serve as suitable replacements and provide the 
    same functionality?
4. How likely is it that external environmental changes will force the project to act 
    on the dependency's abandonment?

For each question, I want you to provide a score on a scale from 1 to 5, where 
1 is the least important, difficult, or likely, and 5 is the most important, 
difficult, or likely. Along with the score, please provide detailed, specific reasoning 
behind the score. Finally, please provide a final recommendation from one of 
the following options:

1. Immediate action is necessary
2. Action is advisable
3. No immediate action is necessary

You should also provide detailed, specific reasoning for your final recommendation.

The project I want to ask is {repo} and the dependency I want to ask is {dep}.
{repo} appears to have {n_files_dep} files where {dep} is used.

I provide relevant context as follows:

[start of README.md]
{readme}
[end of README.md]
"""


class AbandabotReport(TypedDict):
    class Dimension(TypedDict):
        score: int
        reasoning: str

    importance: Dimension
    integration: Dimension
    alternatives: Dimension
    likelihood: Dimension
    recommendation: str
    recommendation_reasoning: str


def get_dir_tree(dir_path: str, prefix: str = "") -> Iterator[str]:
    """A recursive generator, given a directory string,
    will yield a visual tree structure line by line
    with each line prefixed by the same characters

    Args:
        dir_path (str): The directory path
        prefix (str, optional): The prefix to use. Defaults to ''.

    Returns:
        Iterator[str]: The tree structure line by line
    """
    # prefix components:
    space = "    "
    branch = "│   "
    # pointers:
    tee = "├── "
    last = "└── "

    dir_path = Path(dir_path)
    contents = list(dir_path.iterdir())
    # contents each get pointers that are ├── with a final └── :
    pointers = [tee] * (len(contents) - 1) + [last]
    for pointer, path in zip(pointers, contents):
        if path.name.startswith("."):
            continue
        yield prefix + pointer + path.name
        if path.is_dir():  # extend the prefix and recurse:
            extension = branch if pointer == tee else space
            # i.e. space because last, └── , above so no more |
            yield from get_dir_tree(path, prefix=prefix + extension)


def build_abandabot_prompt(
    repo: str, dep: str, context: dict[str, set[int]], context_window: int = 5
) -> str:
    """Build a prompt for Abandabot

    Args:
        repo (str): The repository name
        dep (str): The dependency name
        context (dict[str, set[int]]): A dictionary of file names
            and line numbers where the dependency is used
        context_window (int, optional): The number of lines to include
            per dependency usage. Defaults to 5.

    Returns:
        str: The prompt for Abandabot
    """
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    encoding = {"encoding": "utf-8", "errors": "ignore"}

    if os.path.exists(os.path.join(repo_path, "README.md")):
        with open(os.path.join(repo_path, "README.md"), "r", **encoding) as f:
            readme = f.read()
        # only keep the first 100 lines of the README
        readme = "\n".join(readme.split("\n")[:50]) + "\n...\n"
    else:
        readme = "NOT FOUND"

    # tree = list(get_dir_tree(repo_path))

    prompt = PROMPT_BASE.format(
        dep=dep,
        repo=repo,
        readme=readme,
        # n_files=len(tree),
        n_files_dep=len(context),
    )

    for file, linenos in context.items():
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

        prompt += f"\n[start of {file}]\n{code}[end of {file}]\n"

    return prompt


def generate_report(repo: str, dep: str, context: dict[str, set[int]]) -> None:
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
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
