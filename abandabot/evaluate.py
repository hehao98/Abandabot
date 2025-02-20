import os
import json
import pymongo
import logging
import subprocess
import pandas as pd
import multiprocessing as mp
import sklearn.metrics as skm

from collections import defaultdict
from abandabot import REPORT_PATH, MONGO_URI


def run_one(
    repo: str,
    dep: str,
    model: str,
    include_reasoning: bool,
    include_context: bool,
    complex_reasoning: bool,
    run_id: int,
) -> None:
    with pymongo.MongoClient(MONGO_URI) as client:
        collection = client.abandabot.reports
        if collection.find_one(
            {
                "repo": repo,
                "dep": dep,
                "model": model,
                "include_reasoning": include_reasoning,
                "include_context": include_context,
                "complex_reasoning": complex_reasoning,
                "run_id": run_id,
            }
        ):
            logging.info("Report %s %s %s already exists", repo, dep, model)
            return

    command = [
        "poetry",
        "run",
        "python",
        "-m",
        "abandabot",
        "--github",
        repo,
        "--dep",
        dep,
        "--model",
        model,
    ]

    if include_reasoning:
        command += ["--include-reasoning"]
    if include_context:
        command += ["--include-context"]
    if complex_reasoning:
        command += ["--complex-reasoning"]

    logging.info("Evaluating %s %s", repo, dep)
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        logging.error("Error: %s", e)
        return

    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    report_file = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")
    with open(report_file, "r") as f:
        report: dict = json.load(f)

    if report is None:
        logging.error("Report for %s %s is empty", repo, dep)
        return

    with pymongo.MongoClient(MONGO_URI) as client:
        collection = client.abandabot.reports
        collection.insert_one(
            {
                "repo": repo,
                "dep": dep,
                "model": model,
                "include_reasoning": include_reasoning,
                "include_context": include_context,
                "complex_reasoning": complex_reasoning,
                "run_id": run_id,
                "report": report,
            }
        )

    logging.info(
        "Evaluation for %s in %s: impactful=%s, reasoning=%s",
        dep,
        repo,
        report.get("impactful"),
        report.get("reasoning"),
    )


def collect_reports(
    ground_truth: pd.DataFrame,
    model: str,
    include_reasoning: bool,
    include_context: bool,
    complex_reasoning: bool,
    run_id: int,
) -> pd.DataFrame:
    summary = []

    for repo, dep, dep_eval in zip(
        ground_truth["repo"],
        ground_truth["dep"],
        ground_truth["impactful"],
    ):
        key = {
            "repo": repo,
            "dep": dep,
            "model": model,
            "include_reasoning": include_reasoning,
            "include_context": include_context,
            "complex_reasoning": complex_reasoning,
            "run_id": run_id,
        }
        with pymongo.MongoClient(MONGO_URI) as client:
            report = client.abandabot.reports.find_one(key)
        if (
            report is None
            or report["report"] is None
            or "impactful" not in report["report"]
        ):
            logging.warning("Report %s not found, skipping", key)
            continue
        else:
            report = report["report"]
        if "impactful" not in report:
            logging.warning("Report %s is incomplete, skipping", key)
            continue

        ai_eval = "Yes" if report["impactful"] else "No"
        logging.info(
            "%s %s: dev_eval=%s, ai_eval=%s",
            repo,
            dep,
            dep_eval,
            ai_eval,
        )
        summary.append(
            {
                "repo": repo,
                "dep": dep,
                "dev_eval": dep_eval,
                "ai_eval": ai_eval,
                "report": json.dumps(report),
            }
        )

    return pd.DataFrame(summary)


def evaluate_performance(
    ground_truth: pd.Series, report: pd.Series, true_label: str, false_label: str
) -> dict[str, float]:
    if len(ground_truth) != len(report):
        logging.error("Length of ground_truth and report not match")
        return

    return {
        "yes_precision": skm.precision_score(
            ground_truth,
            report,
            pos_label=true_label,
            zero_division=0,
        ),
        "yes_recall": skm.recall_score(
            ground_truth,
            report,
            pos_label=true_label,
            zero_division=0,
        ),
        "yes_f1": skm.f1_score(
            ground_truth,
            report,
            pos_label=true_label,
            zero_division=0,
        ),
        "no_precision": skm.precision_score(
            ground_truth,
            report,
            pos_label=false_label,
            zero_division=0,
        ),
        "no_recall": skm.recall_score(
            ground_truth,
            report,
            pos_label=false_label,
            zero_division=0,
        ),
        "no_f1": skm.f1_score(
            ground_truth,
            report,
            pos_label=false_label,
            zero_division=0,
        ),
        "macro_precision": skm.precision_score(
            ground_truth,
            report,
            labels=[true_label, false_label],
            average="macro",
            zero_division=0,
        ),
        "macro_recall": skm.recall_score(
            ground_truth,
            report,
            labels=[true_label, false_label],
            average="macro",
            zero_division=0,
        ),
        "macro_f1": skm.f1_score(
            ground_truth,
            report,
            labels=[true_label, false_label],
            average="macro",
            zero_division=0,
        ),
    }


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )

    if not os.path.exists("ground_truth.csv"):
        logging.error("ground_truth.csv not found, please create one first")
        return

    df = pd.read_csv("ground_truth.csv")
    df = df[df.impactful != "Unsure/Maybe"]

    with pymongo.MongoClient(MONGO_URI) as client:
        client.abandabot.reports.create_index(
            [
                ("repo", 1),
                ("dep", 1),
                ("model", 1),
                ("include_reasoning", 1),
                ("include_context", 1),
                ("complex_reasoning", 1),
                ("run_id", 1),
            ],
            unique=True,
        )

    models = [
        "gpt-4o",
        # "gpt-4o-mini", # bad at long prompts
        "deepseek-v3",
        "llama-v3p3",
        "gemini-2.0",
        # "claude-3-5", # rate limit too problematic
    ]
    ablations = [
        # chain-of-thought is basic, do not need in our evaluation
        # "baseline",
        "reasoning",
        # "context",
        "reasoning+theory",
        "context+reasoning",
        "context+reasoning+theory",
    ]
    n_runs = 10
    perf_summ = defaultdict(list)

    for model in models:
        for ablation in ablations:
            for i in range(n_runs):
                logging.info("Evaluating %s-%s run %d", model, ablation, i)

                with mp.Pool(4) as pool:
                    pool.starmap(
                        run_one,
                        [
                            (
                                repo,
                                dep,
                                model,
                                "reasoning" in ablation,
                                "context" in ablation,
                                "theory" in ablation,
                                i,
                            )
                            for repo, dep in zip(df["repo"], df["dep"])
                        ],
                    )

                summ = collect_reports(
                    df,
                    model,
                    "reasoning" in ablation,
                    "context" in ablation,
                    "theory" in ablation,
                    i,
                )
                pd.DataFrame(summ).to_csv(
                    os.path.join(
                        REPORT_PATH, f"summary-{model}-{ablation}-run-{i}.csv"
                    ),
                    index=False,
                )

                logging.info("Evaluating performance for impactful abandonment")
                perf = {
                    "errors": len(df) - len(summ),
                    **evaluate_performance(
                        summ["dev_eval"],
                        summ["ai_eval"],
                        true_label="Yes",
                        false_label="No",
                    ),
                }
                logging.info("Performance %s+%s: %s", model, ablation, perf)
                perf_summ[f"{model}+{ablation}"].append(perf)

    with open(os.path.join(REPORT_PATH, "performance.json"), "w") as f:
        json.dump(perf_summ, f, indent=2)

    logging.info("Finish!")


if __name__ == "__main__":
    main()
