import os
import json
import logging
import subprocess
import pandas as pd


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
    total, match, mismatch, error = 0, 0, 0, 0

    for repo, dep in zip(df["repo"], df["dep"]):
        report_path = os.path.join("reports", f"{repo.replace('/', '_')}")
        if os.path.exists(os.path.join(report_path, f"report-{dep}.json")):
            logging.info("Skipping %s %s, report already exists", repo, dep)
            continue
        
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

    for repo, dep, est_action in zip(df["repo"], df["dep"], df["estimated_action"]):
        report_path = os.path.join("reports", f"{repo.replace('/', '_')}")
        report_file = os.path.join(report_path, f"report-{dep}.json")
        if not os.path.exists(report_file):
            logging.warning("Report file %s not found, skipping", report_file)
            error += 1
            continue

        with open(report_file, "r") as f:
            report = json.load(f)

        actual_action = report["recommendation"]["recommendation"]
        logging.info(
            "%s %s: estimated=%d, actual=%d",
            repo,
            dep,
            est_action,
            actual_action,
        )
        total += 1
        if est_action == actual_action:
            match += 1
        else:
            mismatch += 1

    logging.info(
        "Total: %d, Match: %d, Mismatch: %d, Error: %d", total, match, mismatch, error
    )


if __name__ == "__main__":
    main()
