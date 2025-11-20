"""
Celery Tasks for Evaluation - Distributed processing of F1 fan submission evaluations.

This module sets up Celery workers that:
- Connect to Redis as a message broker
- Receive evaluation tasks from a queue
- Process submissions using the ProcessEvaluation class
- Track metrics (active tasks, completion times)

Celery enables distributed, parallel processing across multiple workers/machines.

To run a worker:
    celery -A deploy.tasks_eval worker --loglevel=INFO --concurrency=10

To enqueue tasks:
    See deploy/enqueue_eval_tasks.py
"""

import asyncio
import logging
import os
import ssl
import time
from typing import Tuple
from urllib.parse import quote_plus

from celery import Celery
from celery.signals import task_postrun, task_prerun

from eval.process_eval import ProcessEvaluation

# ------------------- Logging --------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ------------------- Environment Variables --------------------
def load_env_variables():
    """
    Load environment variables from .env file.

    Reads the .env file and sets environment variables for:
    - Redis connection (host, port, TLS settings)
    - Database connection (Postgres or SQLite)
    - Celery configuration

    This allows you to configure the system without changing code.
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


# Load env variables at module import time
load_env_variables()


# ------------------- Celery Setup --------------------
# Build Redis connection URL from environment variables
use_tls = os.getenv("REDIS_USE_TLS", "false").lower() == "true"
redis_host = quote_plus(os.getenv("REDIS_HOST", "localhost"))
redis_port = os.getenv("REDIS_PORT", 6379)
redis_db = os.getenv("REDIS_DB", 0)
protocol = "rediss" if use_tls else "redis"  # rediss = redis with TLS

REDIS_URL = f"{protocol}://{redis_host}:{redis_port}/{redis_db}"

# Create Celery application
# Celery handles task queuing, distribution, and execution across workers
celery_app = Celery("f1_fan_eval_tasks", broker=REDIS_URL, backend=REDIS_URL)

# Configure TLS/SSL if enabled
if use_tls:
    ssl_options = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.broker_use_ssl = ssl_options
    celery_app.conf.redis_backend_use_ssl = ssl_options
    logger.info("🔐 TLS enabled for Redis broker/backend.")

# Celery configuration
celery_app.conf.update(
    task_routes={"process_one_evaluation_task": {"queue": "eval_queue"}},  # Route task to specific queue
    task_serializer="json",        # Serialize task data as JSON
    result_serializer="json",      # Serialize results as JSON
    accept_content=["json"],       # Only accept JSON content
    task_default_queue="eval_queue",  # Default queue name
)

# ------------------- Database URL --------------------
# Build database connection string from environment variables
use_ssl = os.getenv("POSTGRES_USE_SSL", "false").lower() == "true"
username = quote_plus(os.getenv("POSTGRES_USERNAME", "postgres"))
pwd = os.getenv("POSTGRES_PASSWORD", "")
host = os.getenv("POSTGRES_HOST", "localhost")
db = os.getenv("DBNAME", "f1-fans-eval-db")
port = os.getenv("POSTGRES_PORT", "5432")

# Default to SQLite if no password is set (indicates local development)
DB_URL = "sqlite:///f1_fans_eval.db"
if pwd:
    # Use PostgreSQL if password is configured
    encoded_pwd = quote_plus(pwd)
    ssl_suffix = "?sslmode=require" if use_ssl else ""
    DB_URL = (
        f"postgresql+psycopg2://{username}:{encoded_pwd}@{host}:{port}/{db}{ssl_suffix}"
    )

# ------------------- Metrics --------------------
# Global metrics for tracking worker performance
_task_count = 0        # Number of tasks completed
_total_time = 0.0      # Total time spent on tasks
_active_tasks = 0      # Number of currently running tasks


# ------------------- Async Runner --------------------
async def run_eval_task(
    processor: ProcessEvaluation, sub_id: str, email: str, description: str
) -> Tuple[str, float]:
    """
    Async wrapper to run evaluation in the event loop.

    Args:
        processor: ProcessEvaluation instance
        sub_id: Submission ID
        email: User email
        description: Text to evaluate

    Returns:
        Tuple of (sub_id, elapsed_time)

    This bridges the gap between Celery (which is synchronous) and
    the async ProcessEvaluation methods.
    """
    return await processor.process_submission((sub_id, email, description))


# ------------------- Celery Task --------------------
@celery_app.task(
    name="process_one_evaluation_task",
    bind=True,                          # Bind task instance as first argument
    autoretry_for=(Exception,),         # Automatically retry on any exception
    max_retries=3,                      # Max 3 retry attempts
    default_retry_delay=10,             # Wait 10 seconds between retries
)
def process_one_evaluation_task(
    self,
    sub_id: str,
    email: str,
    description: str,
    db_url: str = DB_URL,
    override: bool = False,
):
    """
    Celery task to evaluate a single F1 fan submission.

    Args:
        self: Bound task instance (for retry functionality)
        sub_id: Submission ID
        email: User email
        description: Text explaining why they're an F1 fan
        db_url: Database connection string
        override: If True, re-evaluate even if already scored

    Returns:
        Tuple of (sub_id, elapsed_time)

    This task:
    1. Creates a ProcessEvaluation instance
    2. Runs the async evaluation in a new event loop
    3. Tracks timing metrics
    4. Automatically retries on failure
    5. Always cleans up database connection

    Workers pull tasks from the Redis queue and execute them.
    Multiple workers can run simultaneously for parallel processing.
    """
    global _task_count, _total_time
    start = time.perf_counter()
    processor = None

    try:
        logger.info(f"[Celery] Received task for {sub_id}")

        # Create evaluation processor
        processor = ProcessEvaluation(db_url=db_url, override=override)

        # Create new event loop for async operations
        # (Celery workers don't have a running event loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run async evaluation
        result: Tuple[str, float] = loop.run_until_complete(
            run_eval_task(processor, sub_id, email, description)
        )

        # Clean up event loop
        loop.close()

        # Extract results and calculate duration
        sub_id_out, elapsed = result
        duration = time.perf_counter() - start

        # Update metrics if evaluation actually ran (elapsed > 0 means not skipped)
        if elapsed > 0:
            _task_count += 1
            _total_time += duration
            avg = _total_time / _task_count if _task_count else 0
            logger.info(
                f"[Celery] ✅ {sub_id_out} done in {duration:.2f}s | Avg {avg:.2f}s"
            )

        return result

    except Exception as exc:
        logger.error(f"[Celery] ❌ Error on {sub_id}: {exc}")
        # Retry the task (Celery will re-queue it)
        raise self.retry(exc=exc) from exc

    finally:
        # Always close database connection to avoid leaks
        if processor and hasattr(processor, "db"):
            processor.db.close()
            logger.info(f"[Celery] Closed DB connection for {sub_id}")


# ------------------- Task Activity Logging --------------------
# These signal handlers track how many tasks are currently running

@task_prerun.connect
def _on_task_start(**kwargs):
    """Called before each task starts."""
    global _active_tasks
    _active_tasks += 1


@task_postrun.connect
def _on_task_done(**kwargs):
    """Called after each task completes (success or failure)."""
    global _active_tasks
    _active_tasks -= 1
    # Log when all tasks are done (worker is idle)
    if _active_tasks == 0:
        logger.info("✅ All current evaluation tasks completed. Awaiting more...")
