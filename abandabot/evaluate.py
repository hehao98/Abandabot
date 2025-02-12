import os
import json
import logging
import subprocess
import pandas as pd

from abandabot import REPORT_PATH


def run_one(repo, dep):
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    report_file = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")
    if os.path.exists(report_file):
        logging.info("Skipping %s %s, report already exists", repo, dep)
    else:
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
            ],
            check=True,
            stdout=subprocess.PIPE,
        )
    with open(report_file, "r") as f:
        report = json.load(f)
    logging.info(
        "Evaluation for %s in %s: impactful=%s, recommendation=%s",
        dep,
        repo,
        report["impactful"],
        report["recommendation"],
    )


def collect_reports(ground_truth: pd.DataFrame) -> pd.DataFrame:
    summary = []

    for repo, dep, dep_eval, dep_action in zip(
        ground_truth["repo"],
        ground_truth["dep"],
        ground_truth["impactful"],
        ground_truth["action"],
    ):
        report_path = os.path.join("reports", f"{repo.replace('/', '_')}")
        report_file = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")
        if not os.path.exists(report_file):
            logging.warning("Report file %s not found, skipping", report_file)
            continue

        with open(report_file, "r") as f:
            report = json.load(f)

        ai_eval = "Yes" if report["impactful"] else "No"
        ai_action = (
            "Monitor" if "Monitor" in str(report["recommendation"]) else "Action"
        )
        dep_action = "Monitor" if "No" in dep_action else "Action"
        logging.info(
            "%s %s: dev_eval=%s, ai_eval=%s, dep_action=%s, ai_action=%s",
            repo,
            dep,
            dep_eval,
            ai_eval,
            ai_action,
            dep_action,
        )
        summary.append(
            {
                "repo": repo,
                "dep": dep,
                "dev_eval": dep_eval,
                "ai_eval": ai_eval,
                "dev_action": dep_action,
                "ai_action": ai_action,
                "ai_report": json.dumps(report),
            }
        )

    return pd.DataFrame(summary)


def evaluate_performance(
    ground_truth: pd.Series, report: pd.Series, true_label: str, false_label: str
) -> None:
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

    logging.info(
        "total=%d, accuracy=%.4f, precision=%.4f, recall=%.4f",
        total,
        acc,
        precision,
        recall,
    )


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

    for repo, dep in zip(df["repo"], df["dep"]):
        run_one(repo, dep)

    summ = collect_reports(df)
    pd.DataFrame(summ).to_csv(os.path.join(REPORT_PATH, "summary.csv"), index=False)

    logging.info("Evaluating performance for impactful abandonment")
    evaluate_performance(summ["dev_eval"], summ["ai_eval"], "Yes", "No")

    logging.info("Evaluating performance for recommended action")
    evaluate_performance(summ["dev_action"], summ["ai_action"], "Action", "Monitor")

    logging.info("Finish!")


if __name__ == "__main__":
    main()
