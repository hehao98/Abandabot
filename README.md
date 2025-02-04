# Abandabot

Your intelligent assistant that monitors and responds to abandoned dependencies

## Setup

The project works with Python 3.11+ and uses [`poetry`](https://python-poetry.org/) for dependency management. With poetry installed, run the following command to setup the development environment and install all dependencies:

```
poetry install
```

## Basic Usage

```
$ poetry run python -m abandabot.evalaute --github OWNER/REPO [--overwrite]
```
