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
DEEPSEEK_API_KEY="[Your DeepSeek API key]"
GOOGLE_API_KEY="[Your Google API key]"
ANTHROPIC_API_KEY="[Your Anthropic API key]"
```

For TypeScript projects, please also install Node.js and ensure `node` is on the PATH.

## Basic Usage

```
$ poetry run python -m abandabot --github OWNER/REPO --dep DEPENDENCY [--overwrite]
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
