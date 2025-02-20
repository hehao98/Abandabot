# Abandabot

An intelligent assistant that evaluates abandoned dependencies

## Setup

The project works with Python 3.11+ and uses [`poetry`](https://python-poetry.org/) for dependency management. With poetry installed, run the following command to setup the development environment and install all dependencies:

```
poetry install
```

The Abandabot currently uses ChatGPT-4o-mini and needs to have the OPENAI_API_KEY env variable setup in the `.env` file. Optionally, LangSmith config can be added. Example `.env` file:

```
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
LANGSMITH_API_KEY="[Your LangSmith API key]"
LANGSMITH_PROJECT="[Your LangSmith project name]"
OPENAI_API_KEY="[Your OpenAI API key]"
FIREWORKS_API_KEY="[Your Fireworks API key]"
ANTHROPIC_API_KEY="[Your Anthropic API key]"
```

For TypeScript projects, please also install Node.js and ensure `node` is on the PATH.

## Basic Usage

```
$ poetry run python -m abandabot -h
usage: __main__.py [-h] --github GITHUB --dep DEP --model
                   {gpt-4o-mini,gpt-4o,deepseek-v3,llama-v3p1,llama-v3p3,claude-3-5,gemini-2.0} 
                   [--overwrite] [--include-reasoning] [--include-context] [--complex-reasoning] 
                   [--summarize]

options:
  -h, --help            show this help message and exit
  --github GITHUB       GitHub repository in the format 'owner/repo'
  --dep DEP             The abandoned dependency to evaluate (e.g. 'lodash')
  --model {gpt-4o-mini,gpt-4o,deepseek-v3,llama-v3p1,llama-v3p3,claude-3-5,gemini-2.0}
                        The model to use for dependency evaluation
  --overwrite           Overwrite the GitHub repository and CodeQL DB if it already exists
  --include-reasoning   Include multiple dimensions of reasoning for dependency evaluation in the report
  --include-context     Include project and dependency context information in the report
  --complex-reasoning   Include complex reasoning for dependency evaluation in the report
  --summarize           Include a summary of the reasonings in the report
```

It will download CodeQL automatically to the abandabot directory. The current CodeQL version used (v2.20.4) may crash on Windows for certain TypeScript projects, so we recommend using Linux or Mac OS instead for running Abandabot.

## Run Performance Evaluation

```
$ poetry run python -m abandabot.evaluate
```

This requires a ground truth dataset `ground_truth.csv` in the following format:

```
repo,repo_url,dep,impactful,action
abc/def,http://github.com/abc/def,vue,Yes,Immediate action is necessary
...
```

Due to the confidential requirements of our interviews, we cannot share the ground truth we used.
