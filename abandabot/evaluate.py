import os
import json
import logging
import subprocess
import pandas as pd

from abandabot import REPORT_PATH


def run_one(repo: str, dep: str, options: list[str] = []) -> None:
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    report_file = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")
    logging.info("Evaluating %s %s", repo, dep)
    subprocess.run(
        [
            "poetry",
            "run",
            "python",
            "-m",
            "abandabot",
            "--github",
            repo,
            "--dep",
            dep,
            *options,
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    with open(report_file, "r") as f:
        report = json.load(f)
    logging.info(
        "Evaluation for %s in %s: impactful=%s, reasoning=%s",
        dep,
        repo,
        report["impactful"],
        report["reasoning"],
    )


def collect_reports(ground_truth: pd.DataFrame) -> pd.DataFrame:
    summary = []

    for repo, dep, dep_eval in zip(
        ground_truth["repo"],
        ground_truth["dep"],
        ground_truth["impactful"],
    ):
        report_path = os.path.join("reports", f"{repo.replace('/', '_')}")
        report_file = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")
        if not os.path.exists(report_file):
            logging.warning("Report file %s not found, skipping", report_file)
            continue

        with open(report_file, "r") as f:
            report = json.load(f)

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
            }
        )

    return pd.DataFrame(summary)


def evaluate_performance(
    ground_truth: pd.Series, report: pd.Series, true_label: str, false_label: str
) -> dict[str, float]:
    if len(ground_truth) != len(report):
        logging.error("Length of ground_truth and report not match")
        return

    total, tp, fp, tn, fn = len(report), 0, 0, 0, 0
    for dev_eval, ai_eval in zip(ground_truth, report):
        if dev_eval == true_label and ai_eval == true_label:
            tp += 1
        elif dev_eval == false_label and ai_eval == true_label:
            fp += 1
        elif dev_eval == true_label and ai_eval == false_label:
            fn += 1
        elif dev_eval == false_label and ai_eval == false_label:
            tn += 1
    acc, precision, recall = (tp + tn) / (total), tp / (tp + fp), tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall)
    return {"accuracy": acc, "precision": precision, "recall": recall, "f1": f1}


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

    models = ["chatgpt"]  # antropic, deepseek, gemini, llama
    ablations = [
        # "no+context+reasoning",
        # "no+context",
        # "no+reasoning",
        "context+reasoning",
    ]

    for model in models:
        for ablation in ablations:
            logging.info("Evaluating model %s with ablation %s", model, ablation)

            options = []
            if ablation == "no+context+reasoning":
                options = ["--exclude-context", "--exclude-reasoning"]
            elif ablation == "no+context":
                options = ["--exclude-context"]
            elif ablation == "no+reasoning":
                options = ["--exclude-reasoning"]

            for repo, dep in zip(df["repo"], df["dep"]):
                try:
                    run_one(repo, dep, options)
                except Exception as e:
                    logging.error("Error evaluating %s %s: %s", repo, dep, e)

            summ = collect_reports(df)
            summary_path = os.path.join(REPORT_PATH, f"summary-{model}-{ablation}.csv")
            pd.DataFrame(summ).to_csv(summary_path)

            logging.info("Evaluating performance for impactful abandonment")
            perf = evaluate_performance(summ["dev_eval"], summ["ai_eval"], "Yes", "No")
            logging.info("Performance %s+%s: %s", model, ablation, perf)

    logging.info("Finish!")


if __name__ == "__main__":
    main()
