# Abandabot

An intelligent assistant that evaluates abandoned dependencies

## Setup

The project works with Python 3.11+ and uses [`poetry`](https://python-poetry.org/) for dependency management. With poetry installed, run the following command to setup the development environment and install all dependencies:

```
poetry install
```

## Basic Usage

```
$ poetry run python -m abandabot.evaluate --github OWNER/REPO [--overwrite]
```
