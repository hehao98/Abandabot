import os
import json
import logging
import requests
import openai
import time

from pathlib import Path
from typing import Iterator, Optional
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langchain_fireworks import ChatFireworks
from langchain_anthropic import ChatAnthropic
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.exceptions import OutputParserException
from abandabot import REPO_PATH, REPORT_PATH


PROMPT_BASE_NO_REASONING = """
You are an expert JavaScript developer building a tool to notify a project's maintainers 
when one of the project's dependencies becomes abandoned. However, instead of notifying
them when any of their dependencies are abandoned, you want to only notify them about 
the abandonment of dependencies that are likely important and impactful to the project,
{context} so as to minimize notification fatigue. 

Your response should contain and only contain a parsable JSON document. 
In the boolean "impactful" field of your JSON document, please provide a final impact evaluation, 

1. true: The dependencies' abandonment would likely be directly impactful to the project
2. false: The dependencies' abandonment would not likely be directly impactful to the project

The project I want to ask is {repo} and the dependency I want to ask is {dep}.
"""

PROMPT_BASE_REASONING = """
You are an expert JavaScript developer building a tool to notify a project's maintainers 
when one of the project's dependencies becomes abandoned. However, instead of notifying
them when any of their dependencies are abandoned, you want to only notify them about 
the abandonment of dependencies that are likely important and impactful to the project
{context} so as to minimize notification fatigue. 

Your response should contain and only contain a parsable JSON document.
In the top-level "reasoning" field of your JSON document, you should provide detailed,
specific reasoning for your impact evaluation.

Based on your reasoning, please provide a final impact evaluation, in the boolean 
"impactful" field of your JSON document:

1. true: The dependencies' abandonment would likely be directly impactful to the project
2. false: The dependencies' abandonment would not likely be directly impactful to the project

The project I want to ask is {repo} and the dependency I want to ask is {dep}.
"""

PROMPT_BASE_COMPLEX_REASONING_NO_CONTEXT = """
You are an expert JavaScript developer building a tool to notify a project's maintainers 
when one of the project's dependencies becomes abandoned. However, instead of notifying
them when any of their dependencies are abandoned, you want to only notify them about 
the abandonment of dependencies that are likely important and impactful to the project,
so as to minimize notification fatigue. 

I am going to ask you important dependency management questions regarding whether 
a dependency's future hypothetical abandonment is likely to be impactful and therefore 
noteworthy to the project. I want you to answer the following four questions:

1. How important is the functionality provided by the dependency to the project? 
2. How difficult is it to replace the dependency, considering the depth of its 
    integration in the project's code base?
3. How difficult is it to replace the dependency, considering the availability of 
    alternative packages that could serve as suitable replacements and provide the 
    same functionality?
4. How likely is it that external environmental changes will force the project to act 
    on the dependency's abandonment?

For each question, I want you to provide a score on a scale from 1 to 5, where 
1 is the least important, difficult, or likely, and 5 is the most important, 
difficult, or likely. Along with the score, please provide detailed, specific reasoning 
behind the score. Your response for each question should be placed in the top-level "importance", 
"integration", "alternatives", and "likelihood" fields of your JSON response, respectively.
For each of these fields, you should provide a "score" field with the score you assigned
to the question, and a "reasoning" field with your detailed, specific reasoning.

Cnsidering all your above answers, please provide detailed, specific reasoning for
whether the dependency abandabot would be impactful, in the top-level "reasoning" 
field of your JSON response. Finally, provide a final impact 
evaluation, in the boolean top-level "impactful" field of your JSON response:

1. true: The dependencies' abandonment would likely be directly impactful to the project
2. false: The dependencies' abandonment would not likely be directly impactful to the project 

The project I want to ask is {repo} and the dependency I want to ask is {dep}.
"""

PROMPT_BASE_COMPLEX_REASONING = """
You are an expert JavaScript developer building a tool to notify a project's maintainers 
when one of the project's dependencies becomes abandoned. However, instead of notifying
them when any of their dependencies are abandoned, you want to only notify them about 
the abandonment of dependencies that are likely important and impactful to the project 
given the context of their dependency usage, so as to minimize notification fatigue. 

I am going to ask you important dependency management questions regarding whether 
a dependency's future hypothetical abandonment is likely to be impactful and therefore 
noteworthy to the project. For context, I will provide you with
the project's README file, the dependency's README file, the package.json file, an 
overview of dependency usage in this project, and partial code snippets from 
this project where the dependency is used. I want you to answer the following four 
questions based on the information I provided:

1. How important is the functionality provided by the dependency to the project? 
2. How difficult is it to replace the dependency, considering the depth of its 
    integration in the project's code base?
3. How difficult is it to replace the dependency, considering the availability of 
    alternative packages that could serve as suitable replacements and provide the 
    same functionality?
4. How likely is it that external environmental changes will force the project to act 
    on the dependency's abandonment?

For each question, I want you to provide a score on a scale from 1 to 5, where 
1 is the least important, difficult, or likely, and 5 is the most important, 
difficult, or likely. Along with the score, please provide detailed, specific reasoning 
behind the score. Your response for each question should be placed in the top-level "importance", 
"integration", "alternatives", and "likelihood" fields of your JSON response, respectively.
For each of these fields, you should provide a "score" field with the score you assigned
to the question, and a "reasoning" field with your detailed, specific reasoning.

Cnsidering all your above answers, please provide detailed, specific reasoning for
whether the dependency abandabot would be impactful, in the top-level "reasoning" 
field of your JSON response. Finally, provide a final impact 
evaluation, in the boolean top-level "impactful" field of your JSON response:

1. true: The dependencies' abandonment would likely be directly impactful to the project
2. false: The dependencies' abandonment would not likely be directly impactful to the project 

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


PROMPT_SUMMARY = """
Based on your responses, please provide a summary of your reasoning for each of the
four dimensions of importance, integration, alternatives, and likelihood, as well as
a summary of your overall reasoning for whether the dependency abandabot would be impactful.
Your response should contain and only contain a parsable JSON document.
In the top-level "importance_summary", "integration_summary", "alternatives_summary",
"likelihood_summary", and "reasoning_summary" fields of your JSON document, please provide
a summary of your reasoning for each of the four dimensions and the overall reasoning, respectively.
"""


class AbandabotReportNoReasoning(TypedDict):
    impactful: bool


class AbandabotReportReasoning(TypedDict):
    reasoning: str
    impactful: bool


class AbandabotReport(TypedDict):
    class Dimension(TypedDict):
        reasoning: str
        score: int

    importance: Dimension
    integration: Dimension
    alternatives: Dimension
    likelihood: Dimension
    reasoning: str
    impactful: bool


class AbandabotReportSummary(TypedDict):
    importance_summary: str
    integration_summary: str
    alternatives_summary: str
    likelihood_summary: str
    reasoning_summary: str


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
    include_reasoning: bool = False,
    include_context: bool = False,
    complex_reasoning: bool = False,
    context: dict[str, dict[str, set[int]]] = dict(),
    context_window: int = 5,
) -> str:
    """Build a prompt for Abandabot

    Args:
        repo (str): The repository name
        dep (str): The dependency name
        include_reasoning (bool, optional): Whether to include into the prompt
            the four dimensions developers often consider for abandonment.
            Defaults to False.
        include_context (bool, optional): Whether to include into the prompt
            the context of the repository and dependency. Defaults to False.
        complex_reasoning (bool, optional): Whether to include into the prompt
            the four dimensions developers often consider for abandonment
            with detailed JSON formatted reasoning. Defaults to False.
            If True, include_reasoning and include_conetxt must be True.
        context (dict[str, dict[str, set[int]]]): A dictionary mapping dependencies to files
            and line numbers where the dependency is used. Defaults to an empty dict.
        context_window (int, optional): The number of lines to include
            per dependency usage. Defaults to 5.

    Returns:
        str: The prompt for Abandabot
    """
    repo_path = os.path.join(REPO_PATH, repo.replace("/", "_"))
    encoding = {"encoding": "utf-8", "errors": "ignore"}

    if include_context:
        context_msg = "given the context of their dependency usage,"
    else:
        context_msg = ""
        repo = "##anonymous##"

    if include_reasoning and not complex_reasoning:
        prompt = PROMPT_BASE_REASONING.format(repo=repo, dep=dep, context=context_msg)
    elif include_reasoning and not include_context and complex_reasoning:
        prompt = PROMPT_BASE_COMPLEX_REASONING_NO_CONTEXT.format(repo=repo, dep=dep)
    elif include_reasoning and include_context and complex_reasoning:
        prompt = PROMPT_BASE_COMPLEX_REASONING.format(repo=repo, dep=dep)
    else:
        prompt = PROMPT_BASE_NO_REASONING.format(
            repo=repo, dep=dep, context=context_msg
        )

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
    for dep2, dep_context in context.items():
        if dep != dep2:
            continue
        dep_usage_overview += f"{dep2}\n"
        for file, linenos in dep_context.items():
            dep_usage_overview += f"  {file}:{','.join(sorted(map(str, linenos)))}\n"
    dep_usage_overview = dep_usage_overview[:-1]

    prompt += PROMPT_CONTEXT.format(
        readme=readme,
        dep_readme=dep_readme,
        package_json=package_json,
        dep_usage_overview=dep_usage_overview,
    )

    if dep not in context:
        logging.warning("No context found for %s, found are: %s", dep, context.keys())
        return prompt

    for file, linenos in context[dep].items():
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
    model_name: str,
    include_reasoning: bool = False,
    include_context: bool = False,
    complex_reasoning: bool = False,
    summarize: bool = False,
    context: dict[str, dict[str, set[int]]] = dict(),
    context_window: int = 5,
) -> None:
    """Generate an abandonment report for a dependency in a repository

    Args:
        repo (str): The repository name
        dep (str): The dependency name
        model_name (str): The model name to use for the report
        include_reasoning (bool, optional): Whether to include into the prompt
            the four dimensions developers often consider for abandonment.
            Defaults to True.
        include_context (bool, optional): Whether to include into the prompt
            the context of the repository and dependency. Defaults to True.
        complex_reasoning (bool, optional): Whether to include into the prompt
            the four dimensions developers often consider for abandonment
            with detailed JSON formatted reasoning. Defaults to False.
            If True, include_reasoning must be True.
        summarize: (bool, optional): Whether to summarize the report. Defaults to False.
            This would leverage LangChain’s memory to save first round of output.
            May not work for every model. If True, include_reasoning must be True.
        context (dict[str, dict[str, set[int]]]): A dictionary mapping dependencies to files
            and line numbers where the dependency is used Defaults to an empty dict.
        context_window (int, optional): The number of lines to include
            per dependency usage. Defaults to 5.

    Returns:
        None
    """
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    prompt_path = os.path.join(report_path, f"prompt-{dep.replace('/', '_')}.txt")
    output_path = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")

    if not include_reasoning and complex_reasoning:
        raise ValueError("If complex_reasoning=True, include_reasoning must be True")
    if not include_reasoning and summarize:
        raise ValueError("If summarize=True, include_reasoning must be True")

    if model_name == "gpt-4o-mini":
        base_model = ChatOpenAI(model="gpt-4o-mini")
    elif model_name == "gpt-4o":
        base_model = ChatOpenAI(model="gpt-4o")
    elif model_name == "deepseek-v3":
        base_model = ChatFireworks(model="accounts/fireworks/models/deepseek-v3")
    elif model_name == "llama-v3p1":
        base_model = ChatFireworks(model="accounts/fireworks/models/llama-v3p1-70b-instruct")
    elif model_name == "llama-v3p3":
        base_model = ChatFireworks(model="accounts/fireworks/models/llama-v3p3-70b-instruct")
    elif model_name == "claude-3-5":
        base_model = ChatAnthropic(model="claude-3-5-sonnet-20241022")
    elif model_name == "gemini-2.0":
        base_model = ChatVertexAI(model="gemini-2.0-flash")
    else:
        raise ValueError(f"Unsupported model: {model_name}")

    output_format = AbandabotReportNoReasoning
    if include_reasoning:
        if complex_reasoning:
            output_format = AbandabotReport
        else:
            output_format = AbandabotReportReasoning
    model = base_model.with_structured_output(output_format)

    logging.info("Generating report for %s using %s", repo, model_name)
    prompt = build_abandabot_prompt(
        repo,
        dep,
        include_reasoning,
        include_context,
        complex_reasoning,
        context,
        context_window,
    )
    with open(prompt_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(prompt)
    logging.info("Prompt saved to %s", prompt_path)

    output = None
    for _ in range(3):  # Max 3 retries
        try:
            output = model.invoke(prompt)
            break
        except OutputParserException as ex:
            logging.error("Failed to parse output: %s", ex)
        except openai.RateLimitError as ex:
            logging.error("OpenAI rate limit exceeded: %s", ex)
            time.sleep(10)

    if summarize:
        summary_model = base_model.with_structured_output(AbandabotReportSummary)
        summary_output = summary_model.invoke(
            [
                HumanMessage(prompt),
                AIMessage(json.dumps(output, indent=4)),
                HumanMessage(PROMPT_SUMMARY),
            ]
        )
        output["summary"] = summary_output

    with open(output_path, "w") as f:
        f.write(json.dumps(output, indent=2))
    logging.info("Report saved to %s", output_path)
