import pandas as pd

from langchain_core.prompts import PromptTemplate


def build_abandabot_prompt(
    repo: str, dep: str, dep_usage: pd.DataFrame
) -> PromptTemplate:
    raise NotImplementedError("Not implemented")
