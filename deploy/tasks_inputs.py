"""
Celery Tasks for Input Processing - Distributed ingestion of F1 fan submissions.

This module sets up Celery workers that:
- Connect to Redis as a message broker
- Receive input processing tasks from a queue
- Insert submissions into the database
- Track processing metrics

This is the first step in the pipeline - loading raw submission data.

To run a worker:
    celery -A deploy.tasks_inputs worker --loglevel=INFO --concurrency=6

To enqueue tasks:
    See deploy/enqueue_input_tasks.py
"""

import logging
import os
import ssl
import time
from urllib.parse import quote_plus

from celery import Celery
from celery.signals import task_postrun, task_prerun

from input_processor.process_inputs import ProcessInputs

# ------------------- Logging --------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ------------------- Env Loader --------------------
def load_env_variables():
    """
    Load environment variables from .env file.

    Configures Redis connection, database URL, and Celery settings
    without modifying code.
    """
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value.strip('"')
        logger.info(f"Loaded environment variables from {env_file}")
    else:
        logger.warning("⚠️ No .env file found. Using defaults.")


# Load configuration at module import time
load_env_variables()

# ------------------- Redis / Celery Setup --------------------
# Build Redis connection URL from environment
use_tls = os.getenv("REDIS_USE_TLS", "false").lower() == "true"
redis_host = quote_plus(os.getenv("REDIS_HOST", "localhost"))
redis_port = os.getenv("REDIS_PORT", 6379)
redis_db = os.getenv("REDIS_DB", 0)
protocol = "rediss" if use_tls else "redis"

REDIS_URL = f"{protocol}://{redis_host}:{redis_port}/{redis_db}"

# Create Celery application for input processing
celery_app = Celery("process_input_tasks", broker=REDIS_URL, backend=REDIS_URL)

# Configure TLS if enabled
if use_tls:
    ssl_options = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.broker_use_ssl = ssl_options
    celery_app.conf.redis_backend_use_ssl = ssl_options
    logger.info("🔐 TLS enabled for Redis broker/backend.")

# Celery configuration
# Note: This uses a different queue ("inputs_queue") than evaluation tasks
celery_app.conf.update(
    task_routes={"process_one_submission_task": {"queue": "inputs_queue"}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue="inputs_queue",
)

# ------------------- Database URL --------------------
# Build database connection string (same logic as tasks_eval.py)
use_ssl = os.getenv("POSTGRES_USE_SSL", "false").lower() == "true"
username = quote_plus(os.getenv("POSTGRES_USERNAME", "postgres"))
pwd = os.getenv("POSTGRES_PASSWORD", "")
host = os.getenv("POSTGRES_HOST", "localhost")
db = os.getenv("DBNAME", "f1-fans-eval-db")
port = os.getenv("POSTGRES_PORT", "5432")

DB_URL = "sqlite:///f1_fans_eval.db"
if pwd:
    encoded_pwd = quote_plus(pwd)
    ssl_suffix = "?sslmode=require" if use_ssl else ""
    DB_URL = (
        f"postgresql+psycopg2://{username}:{encoded_pwd}@{host}:{port}/{db}{ssl_suffix}"
    )

# ------------------- Processor --------------------
# Create a shared processor instance (reused across tasks)
processor = ProcessInputs()

# ------------------- Metrics --------------------
# Track worker performance
_task_count = 0        # Total tasks completed
_total_time = 0.0      # Total processing time
_active_tasks = 0      # Currently running tasks


# ------------------- Celery Task --------------------
@celery_app.task(
    name="process_one_submission_task",
    bind=True,                      # Bind task instance for retry
    autoretry_for=(Exception,),     # Auto-retry on any error
    max_retries=3,                  # Max 3 retries
    default_retry_delay=10,         # Wait 10s between retries
)
def process_one_submission_task(self, sub_id: str, email: str, description: str):
    """
    Celery task to insert a single submission into the database.

    Args:
        self: Bound task instance (for retry functionality)
        sub_id: Submission ID
        email: User email
        description: Text explaining why they're an F1 fan

    Returns:
        Dictionary with status info: {sub_id, status, elapsed}

    This task:
    1. Inserts the submission into the database
    2. Tracks timing metrics
    3. Automatically retries on failure

    This is simpler than evaluation tasks - it's just database insertion.
    Workers pull tasks from the "inputs_queue" and execute them.
    """
    global _task_count, _total_time
    start = time.perf_counter()

    try:
        logger.info(f"[Celery] Processing submission {sub_id} ({email})")

        # Insert submission into database
        _ = processor.db.insert_submission(
            sub_id=sub_id, email=email, description=description
        )

        duration = time.perf_counter() - start

        # Update metrics
        _task_count += 1
        _total_time += duration
        avg = _total_time / _task_count if _task_count else 0
        logger.info(
            f"[Celery] ✅ Finished submission {sub_id} in {duration:.2f}s (avg {avg:.2f}s)"
        )

        return {"sub_id": sub_id, "status": "stored", "elapsed": duration}

    except Exception as exc:
        logger.error(f"[Celery] ❌ Error processing {sub_id}: {exc}")
        # Retry the task (Celery will re-queue it)
        raise self.retry(exc=exc) from exc


# ------------------- Idle Queue Logging --------------------
# Track active tasks for monitoring

@task_prerun.connect
def _on_task_start(**kwargs):
    """Called before each task starts."""
    global _active_tasks
    _active_tasks += 1


@task_postrun.connect
def _on_task_done(**kwargs):
    """Called after each task completes."""
    global _active_tasks
    _active_tasks -= 1
    # Log when worker is idle
    if _active_tasks == 0:
        logger.info("✅ All current input tasks completed. Awaiting more...")
