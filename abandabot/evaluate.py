import os
import json
import logging
import subprocess
import pandas as pd

from abandabot import REPORT_PATH


def run_one(repo, dep):
    report_path = os.path.join(REPORT_PATH, f"{repo.replace('/', '_')}")
    report_file = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")
    # if os.path.exists(report_file):
    #    logging.info("Skipping %s %s, report already exists", repo, dep)
    # else:
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
    total, error, tp, fp, tn, fn = 0, 0, 0, 0, 0, 0

    for repo, dep, dev_eval in zip(
        ground_truth["repo"], ground_truth["dep"], ground_truth["important_abandonment"]
    ):
        report_path = os.path.join("reports", f"{repo.replace('/', '_')}")
        report_file = os.path.join(report_path, f"report-{dep.replace('/', '_')}.json")
        if not os.path.exists(report_file):
            logging.warning("Report file %s not found, skipping", report_file)
            error += 1
            continue

        with open(report_file, "r") as f:
            report = json.load(f)

        ai_eval = "Yes" if report["impactful"] else "No"
        logging.info(
            "%s %s: dev_eval=%s, ai_eval=%s",
            repo,
            dep,
            dev_eval,
            ai_eval,
        )
        summary.append(
            {
                "repo": repo,
                "dep": dep,
                "developer_eval": dev_eval,
                "ai_eval": ai_eval,
            }
        )
        total += 1
        if dev_eval == "Yes" and ai_eval == "Yes":
            tp += 1
        elif dev_eval == "No" and ai_eval == "Yes":
            fp += 1
        elif dev_eval == "Yes" and ai_eval == "No":
            fn += 1
        elif dev_eval == "No" and ai_eval == "No":
            tn += 1

    acc, precision, recall = (tp + tn) / (total - error), tp / (tp + fp), tp / (tp + fn)

    logging.info(
        "total=%d, error=%d, accuracy=%.4f, precision=%.4f, recall=%.4f",
        total,
        error,
        acc,
        precision,
        recall,
    )
    return pd.DataFrame(summary)


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

    for repo, dep in zip(df["repo"], df["dep"]):
        run_one(repo, dep)

    summary = collect_reports(df)
    pd.DataFrame(summary).to_csv(os.path.join(REPORT_PATH, "summary.csv"), index=False)
    logging.info("Finish")


if __name__ == "__main__":
    main()
