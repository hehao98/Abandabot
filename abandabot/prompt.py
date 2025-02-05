import os
import pandas as pd

from typing_extensions import TypedDict

from abandabot import REPO_PATH


PROMPT_BASE = """
You are an expert JavaScript developer. I am going to ask you important dependency 
management questions regarding whether I will need to take action if a dependency gets abandoned.
I will provide you with the project README file, the package.json file, 
the dependency name, and the source code files (or code snippets) in this project 
where the dependency is used. I want you to evaluate the following four dimensions 
regarding the dependency and the project:

1. How important is the dependency to the project? 
2. How difficult is it to replace the dependency, due to its depth of integration?
3. How difficult is it to replace the dependency, due to the lack of alternatives?
4. How likely it is that external changes will force the project to act on its abandonment?

For each question, I want you to provide an answer on a scale from 1 to 5, where 
1 is the least important, difficult, or likely, and 5 is the most important, 
difficult, or likely. Along with the score, please provide detailed, specific reasoning 
behind the score. Finally, please provide a final recommendation from one of 
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
        recommendation: str
        reasoning: str

    importance: Dimension
    integration: Dimension
    alternatives: Dimension
    likelihood: Dimension
    recommendation: Recommendation


def build_abandabot_prompt(repo: str, dep: str, dep_usage: pd.DataFrame) -> str:
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))

    if os.path.exists(os.path.join(repo_path, "README.md")):
        with open(os.path.join(repo_path, "README.md"), "r") as f:
            readme = f.read()
        # only keep the first 15 lines of the README
        readme = "\n".join(readme.split("\n")[:15]) + "\n...\n"
    else:
        readme = "NOT FOUND"

    with open(os.path.join(repo_path, "package.json"), "r") as f:
        pkg_json = f.read()

    prompt = PROMPT_BASE.format(dep=dep, readme=readme, pkg_json=pkg_json)

    for file, uses in dep_usage[dep_usage.name == dep].groupby("file"):
        with open(os.path.join(repo_path, file), "r") as f:
            code_lines = f.read().split("\n")
        code = ""
        for lineno in sorted(uses["useLineno"].tolist()):
            start = max(0, lineno - 5)
            end = min(len(code_lines), lineno + 5)
            code += "\n...\n" + "\n".join(code_lines[start:end]) + "\n...\n"
        prompt += f"\n[start of {file}]\n{code}\n[end of {file}]\n"

    return prompt
