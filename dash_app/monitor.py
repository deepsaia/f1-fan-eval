import logging
import os
import subprocess
import time
from urllib.parse import quote_plus

import redis

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# --- Load environment variables from .env ---
def load_env_variables():
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value.strip('"')
        print("Loaded environment variables from .env")
    else:
        print("No .env file found. Using default environment variables.")


# --- Redis Connection ---
def connect_to_redis():
    use_tls = os.getenv("REDIS_USE_TLS", "false").lower() == "true"
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))

    protocol = "rediss" if use_tls else "redis"
    redis_host_safe = quote_plus(redis_host)
    redis_url = f"{protocol}://{redis_host_safe}:{redis_port}/{redis_db}"
    print(f"Connecting to Redis at {redis_url}")

    try:
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            ssl=use_tls,
            ssl_cert_reqs=None if use_tls else None,
        )
        # Test connection
        r.ping()
        print("Redis connection established successfully")
        return r
    except Exception as e:
        print(f"Redis connection failed: {e}")
        return None


# --- Run shell commands ---
def run_shell_command(cmd):
    try:
        print(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Output:                   {result.stdout.strip()}")
        else:
            print(f"Error:{result.stderr.strip()}")
    except Exception as e:
        print(f"Exception while running command: {cmd}\n{e}")


# --- Main periodic task ---
def run_periodic_tasks():
    load_env_variables()
    redis_client = connect_to_redis()

    interval = 300
    # immediately start the next run
    next_run = time.time()
    try:
        while True:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled task cycle..."
            )
            # logger.info("Starting scheduled task cycle...")

            # Run eval_database commands
            run_shell_command(
                "python eval_database.py --ct --t evaluations --where \"input_type='text'\""
            )
            run_shell_command("python eval_database.py --ct --t submissions")
            run_shell_command("python eval_database.py --ct --t file_status")

            # Check Redis queue length
            if redis_client:
                try:
                    queue_len = redis_client.llen("eval_queue")
                    print(f"Output:                   eval_queue length: {queue_len}")
                except Exception as e:
                    print(f"Failed to get Redis queue length: {e}")
            run_shell_command("python eval_database.py --inc")
            cmd = (
                "python eval_database.py "
                '--query "SELECT count(*), avg(total_processing_time_in_seconds) AS avg_time_fe, '
                "sum(total_cost) as total_cost_fe "
                "FROM evaluations WHERE evaluated_at > timestamp '2025-08-14 00:00' "
                "AND input_type = 'text'\""
            )
            run_shell_command(cmd)
            # run_shell_command("python eval_database.py --ct --t file_status")

            # Schedule next run
            next_run += interval
            sleep_time = max(0, next_run - time.time())
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sleeping for {sleep_time:.1f} seconds...\n"
            )
            # logger.info(f"Sleeping for {sleep_time:.2f} seconds until next cycle...\n")
            time.sleep(sleep_time)
    finally:
        if redis_client:
            redis_client.close()


# --- Entrypoint ---
if __name__ == "__main__":
    run_periodic_tasks()
