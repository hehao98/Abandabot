import os
import json
import logging
import requests

from pathlib import Path
from typing import Iterator, Optional
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from abandabot import REPO_PATH, REPORT_PATH


PROMPT_BASE_NO_DIMENSION = """
You are an expert JavaScript developer. I am going to ask you important dependency 
management questions regarding whether the abandonment is impactful and I will need
to take action, if a dependency gets abandoned. Please provide a final impact 
evaluation, in the "impactful" field of your JSON response, and a recommendation from 
one of the following options, to the "recommendation" field of your JSON response:

1. Action is necessary
2. Monitoring the situation

You should also provide detailed, specific reasoning for your impact evaluation and 
recommendation, in the "reasoning" field of your JSON response.

The project I want to ask is {repo} and the dependency I want to ask is {dep}.
"""

PROMPT_BASE = """
You are an expert JavaScript developer. I am going to ask you important dependency 
management questions regarding whether the abandonment is impactful and I will need
to take action, if a dependency gets abandoned. For context, I will provide you with
the project's README file, the dependency's README file, the package.json file, an 
overview of dependency usage in this project, and partial code snippets from 
this project where the dependency is used. I want you to answer the following four 
questions based on the information I provided:

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
behind the score. Your response for each question should be placed in the "importance", 
"integration", "alternatives", and "likelihood" fields of your JSON response, respectively.
For each of these fields, you should provide a "score" field with the score you assigned
to the question, and a "reasoning" field with your detailed, specific reasoning.

Finally, considering all your above answers, please provide a final impact 
evaluation, in the "impactful" field of your JSON response, and a recommendation from 
one of the following options, to the "recommendation" field of your JSON response:

1. Action is necessary
2. Monitoring the situation

You should also provide detailed, specific reasoning for your impact evaluation and 
recommendation, in the "reasoning" field of your JSON response.

The project I want to ask is {repo} and the dependency I want to ask is {dep}.
"""

PROMPT_CONTEXT = """
I provide relevant context as follows:

[start of project README]
{readme}
[end of project README]

[start of dependency README]
{dep_readme}
[end of dependency README]

[start of package.json]
{package_json}
[end of package.json]

[start of dependency usage overview]
{dep_usage_overview}
[end of dependency usage overview]
"""


class AbandabotReportNoContext(TypedDict):
    impactful: bool
    recommendation: str
    reasoning: str


class AbandabotReport(TypedDict):
    class Dimension(TypedDict):
        score: int
        reasoning: str

    importance: Dimension
    integration: Dimension
    alternatives: Dimension
    likelihood: Dimension
    impactful: bool
    recommendation: str
    reasoning: str


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


def get_dep_readme(dep: str) -> Optional[str]:
    """Try getting the README of a dependency from npm API.
        Returns None if not found.

    Args:
        dep (str): The dependency name

    Returns:
        Optional[str]: The README content
    """
    try:
        response = requests.get(f"https://registry.npmjs.org/{dep}")
        response.raise_for_status()
        readme = response.json().get("readme")
        return readme
    except requests.exceptions.RequestException as e:
        logging.error("Failed to get README for %s: %s", dep, e)
        return None


def build_abandabot_prompt(
    repo: str,
    dep: str,
    include_dimension: bool = False,
    include_context: bool = False,
    context: dict[str, set[int]] = dict(),
    context_window: int = 5,
) -> str:
    """Build a prompt for Abandabot

    Args:
        repo (str): The repository name
        dep (str): The dependency name
        include_dimension (bool, optional): Whether to include into the prompt
            the four dimensions developers often consider for abandonment.
            Defaults to True.
        include_context (bool, optional): Whether to include into the prompt
            the context of the repository and dependency. Defaults to True.
        context (dict[str, set[int]]): A dictionary of file names
            and line numbers where the dependency is used. Defaults to an empty dict.
        context_window (int, optional): The number of lines to include
            per dependency usage. Defaults to 5.

    Returns:
        str: The prompt for Abandabot
    """
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    encoding = {"encoding": "utf-8", "errors": "ignore"}

    if include_dimension:
        prompt = PROMPT_BASE.format(repo=repo, dep=dep)
    else:
        prompt = PROMPT_BASE_NO_DIMENSION.format(repo=repo, dep=dep)

    if not include_context:
        return prompt

    if os.path.exists(os.path.join(repo_path, "README.md")):
        with open(os.path.join(repo_path, "README.md"), "r", **encoding) as f:
            readme = f.read()
        # only keep the first 100 lines of the README
        readme = "\n".join(readme.split("\n")[:100]) + "\n...\n"
    else:
        readme = "NOT FOUND"

    if os.path.exists(os.path.join(repo_path, "package.json")):
        with open(os.path.join(repo_path, "package.json"), "r", **encoding) as f:
            package_json = f.read()
    else:
        package_json = "NOT FOUND"

    dep_readme = get_dep_readme(dep)
    if dep_readme is None:
        dep_readme = "NOT FOUND"

    # tree = list(get_dir_tree(repo_path))

    dep_usage_overview = ""
    for file, linenos in context.items():
        dep_usage_overview += f"{file}: {','.join(sorted(map(str, linenos)))}\n"
    dep_usage_overview = dep_usage_overview[:-1]

    prompt += PROMPT_CONTEXT.format(
        readme=readme,
        dep_readme=dep_readme,
        package_json=package_json,
        dep_usage_overview=dep_usage_overview,
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


def generate_report(
    repo: str,
    dep: str,
    include_dimension: bool = False,
    include_context: bool = False,
    context: dict[str, set[int]] = dict(),
    context_window: int = 5,
) -> None:
    """Generate an abandonment report for a dependency in a repository

    Args:
        repo (str): The repository name
        dep (str): The dependency name
        include_dimension (bool, optional): Whether to include into the prompt
            the four dimensions developers often consider for abandonment.
            Defaults to True.
        include_context (bool, optional): Whether to include into the prompt
            the context of the repository and dependency. Defaults to True.
        context (dict[str, set[int]]): A dictionary of file names
            and line numbers where the dependency is used. Defaults to an empty dict.
        context_window (int, optional): The number of lines to include
            per dependency usage. Defaults to 5.

    Returns:
        None
    """
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    prompt_path = os.path.join(report_path, f"prompt-{dep.replace('/', '_')}.txt")
    output_path = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")

    model_name = "gpt-4o-mini"
    model = ChatOpenAI(model=model_name).with_structured_output(
        AbandabotReport if include_context else AbandabotReportNoContext
    )

    logging.info("Generating report for %s using %s", repo, model_name)
    prompt = build_abandabot_prompt(
        repo, dep, include_dimension, include_context, context, context_window
    )
    with open(prompt_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(prompt)
    logging.info("Prompt saved to %s", prompt_path)

    output = model.invoke(prompt)
    with open(output_path, "w") as f:
        f.write(json.dumps(output, indent=2))
    logging.info("Report saved to %s", output_path)
