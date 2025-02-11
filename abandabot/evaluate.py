import os
import json
import logging
import subprocess
import pandas as pd


def run_one(repo, dep):
    report_path = os.path.join("reports", f"{repo.replace('/', '_')}")
    if os.path.exists(os.path.join(report_path, f"report-{dep}.json")):
        logging.info("Skipping %s %s, report already exists", repo, dep)
        return

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


def collect_reports(ground_truth: pd.DataFrame) -> pd.DataFrame:
    summary = []
    total, match, mismatch, error = 0, 0, 0, 0

    for repo, dep, est_action in zip(
        ground_truth["repo"], ground_truth["dep"], ground_truth["estimated_action"]
    ):
        report_path = os.path.join("reports", f"{repo.replace('/', '_')}")
        report_file = os.path.join(report_path, f"report-{dep}.json")
        if not os.path.exists(report_file):
            logging.warning("Report file %s not found, skipping", report_file)
            error += 1
            continue

        with open(report_file, "r") as f:
            report = json.load(f)

        ai_action = report["recommendation"]
        logging.info(
            "%s %s: estimated=%s, actual=%s",
            repo,
            dep,
            est_action,
            ai_action,
        )
        summary.append(
            {
                "repo": repo,
                "dep": dep,
                "estimated_action": est_action,
                "ai_action": ai_action,
            }
        )
        total += 1
        if est_action == ai_action:
            match += 1
        else:
            mismatch += 1

    logging.info(
        "Total: %d, Match: %d, Mismatch: %d, Error: %d", total, match, mismatch, error
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
    pd.DataFrame(summary).to_csv("summary.csv", index=False)
    logging.info("Finish")


if __name__ == "__main__":
    main()
