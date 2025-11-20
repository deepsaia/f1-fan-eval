import argparse
import logging
import os
from typing import List

from deploy.tasks_inputs import process_one_submission_task
from input_processor.process_inputs import ProcessInputs

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("enqueue_inputs")


def load_env():
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value.strip('"')
        logger.info(f"Loaded environment from {env_file}")
    else:
        logger.warning("⚠️ No .env file found. Using defaults.")


load_env()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Enqueue F1 Fan submission ingestion tasks"
    )
    parser.add_argument(
        "--input-source", required=True, help="Path to the submissions CSV file"
    )
    parser.add_argument("--range", default=None, help="Optional range (e.g. 0-500)")
    return parser.parse_args()


def parse_range(range_str, total):
    try:
        start, end = map(int, range_str.split("-"))
        return max(0, start), min(end + 1, total)
    except Exception as e:
        raise ValueError(f"Invalid range format: {range_str}. Expected N-M.") from e


def main():
    args = parse_args()
    processor = ProcessInputs()
    data = processor.load_input(args.input_source)

    sub_ids: List[str] = data.get("sub_id") or data.get("Respondent ID") or []
    emails: List[str] = data.get(
        "Please share your email address so we can contact you if you win", []
    )
    descriptions: List[str] = data.get(
        "Describe why you believe you are the biggest F1 fan.", []
    )

    total = len(sub_ids)
    if args.range:
        start, end = parse_range(args.range, total)
        sub_ids, emails, descriptions = (
            sub_ids[start:end],
            emails[start:end],
            descriptions[start:end],
        )
        logger.info(f"📊 Range applied: {start}-{end-1} ({len(sub_ids)} records)")

    logger.info(f"🚀 Enqueuing {len(sub_ids)} submissions...")

    for idx, sub_id in enumerate(sub_ids):
        email = emails[idx] if idx < len(emails) else ""
        description = descriptions[idx] if idx < len(descriptions) else ""

        async_result = process_one_submission_task.delay(sub_id, email, description)
        logger.info(
            f"📤 [{idx+1}/{total}] Enqueued {sub_id} ({email}) — Task ID {async_result.id}"
        )

    logger.info(f"✅ All {len(sub_ids)} submission ingestion tasks enqueued.")


if __name__ == "__main__":
    main()
