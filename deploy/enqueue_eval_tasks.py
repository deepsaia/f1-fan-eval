import argparse
import logging
import os
from urllib.parse import quote_plus

from deploy.tasks_eval import process_one_evaluation_task
from eval.process_eval import ProcessEvaluation

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("enqueue_eval_tasks")


def load_env():
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value.strip('"')
        logger.info(f"Loaded {env_file}")
    else:
        logger.warning("⚠️ No .env file found. Using defaults.")


load_env()


def parse_args():
    parser = argparse.ArgumentParser(description="Enqueue F1 Fan evaluation tasks")
    parser.add_argument(
        "--filter-source",
        default=None,
        help="Optional CSV/JSON/TXT file with submission_ids",
    )
    parser.add_argument(
        "--override", action="store_true", help="Re-evaluate even if already done"
    )
    parser.add_argument("--range", default=None, help="Range to enqueue (e.g., 0-100)")
    parser.add_argument(
        "--sid", default=None, help="Specific sub_id(s), comma-separated"
    )
    parser.add_argument("--dbname", default=os.getenv("DBNAME", "f1-fans-eval-db"))
    return parser.parse_args()


def parse_range(range_str, total):
    try:
        start, end = map(int, range_str.split("-"))
        return max(0, start), min(end + 1, total)
    except Exception as e:
        raise ValueError(f"Invalid range: {range_str} (expected format N-M)") from e


def parse_sid_list(sid_arg: str):
    if not sid_arg:
        return []
    seen, out = set(), []
    for sid in [s.strip() for s in sid_arg.split(",") if s.strip()]:
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def build_db_url():
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    if pwd:
        encoded_pwd = quote_plus(pwd)
        user = quote_plus(os.getenv("POSTGRES_USERNAME", "postgres"))
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("DBNAME", "f1-fans-eval-db")
        return f"postgresql+psycopg2://{user}:{encoded_pwd}@{host}:{port}/{db}"
    return "sqlite:///f1_fans_eval.db"


def main():
    args = parse_args()
    db_url = build_db_url()
    logger.info(f"📡 Using DB: {args.dbname}")

    processor = ProcessEvaluation(db_url=db_url, override=args.override)
    submissions = processor.get_submissions_to_process()
    if not submissions:
        logger.info("✅ No pending submissions to enqueue.")
        return

    # Filter by sid if provided
    if args.sid:
        sid_list = parse_sid_list(args.sid)
        submissions = [s for s in submissions if s[0] in sid_list]
        logger.info(f"🎯 Enqueueing specific submissions: {sid_list}")

    # Range slicing
    if args.range:
        start, end = parse_range(args.range, len(submissions))
        submissions = submissions[start:end]
        logger.info(f"📊 Range applied: {start}-{end-1}")

    # Enqueue each
    for sub_id, email, description in submissions:
        result_async = process_one_evaluation_task.delay(
            sub_id, email, description, db_url, args.override
        )
        logger.info(f"➡️ Enqueued {sub_id} (Task ID: {result_async.id})")

    logger.info(f"✅ {len(submissions)} tasks enqueued successfully.")


if __name__ == "__main__":
    main()
