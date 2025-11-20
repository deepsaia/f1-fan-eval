"""
Process Evaluation - Async orchestration for AI-based F1 fan submission scoring.

This module handles the core evaluation pipeline:
1. Fetch submissions from database
2. Create AI clients for each scoring dimension (knowledge, enthusiasm, humor)
3. Send submissions to AI agents asynchronously
4. Collect scores and token metrics
5. Store results in database

Key features:
- Async/parallel processing for speed
- Retry logic for failed AI calls
- Semaphore-based concurrency control (to avoid overwhelming AI server)
- Token/cost tracking for each evaluation
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from db.eval_database import EvalDatabase
from eval.simple_client import SimpleClient
from utils.dual_logger import DualLogger

# Retry configuration for failed AI calls
MAX_RETRIES = 3        # Try up to 3 times if AI call fails
RETRY_DELAY = 2        # Wait 2 seconds between retries

# Field names for evaluation results
SCORE_FIELDS = ["knowledge", "enthusiasm", "humor", "brief_description"]

# Token tracking fields (for monitoring API usage and cost)
TOKEN_FIELDS = [
    "total_tokens",              # Total tokens used (prompt + completion)
    "prompt_tokens",             # Tokens in the input
    "completion_tokens",         # Tokens in the AI's response
    "successful_requests",       # Number of successful API calls
    "total_cost",                # Estimated cost in dollars
    "time_taken_in_seconds",     # Time for AI processing
]

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


class ProcessEvaluation:
    """
    Main orchestrator for evaluating F1 fan submissions.

    This class:
    - Connects to the database
    - Fetches submissions that need evaluation
    - Creates AI clients (one per score dimension)
    - Processes submissions asynchronously with concurrency control
    - Stores evaluation results back to database

    Usage:
        processor = ProcessEvaluation(db_url="sqlite:///f1_fans_eval.db")
        asyncio.run(processor.run())
    """

    def __init__(
        self,
        db_url: str = None,
        override: bool = False,
        filter_ids: Set[str] = None,
        concurrency_limit: int = 8,
        local_test: bool = False,
        granular: bool = False,
    ):
        """
        Initialize the evaluation processor.

        Args:
            db_url: Database connection string (defaults to SQLite)
            override: If True, re-evaluate submissions that already have scores
            filter_ids: Optional set of submission IDs to process (if empty, process all)
            concurrency_limit: Max number of simultaneous AI evaluations
            local_test: If True, use local test mode (for development)
            granular: If True, use separate AI clients per score type (not currently used)
        """
        # Connect to database
        self.db = EvalDatabase(db_url)

        # Store configuration
        self.override = override
        self.filter_ids = filter_ids if filter_ids else set()

        # Concurrency control: limit how many AI calls run at once
        # This prevents overwhelming the AI server
        concurrency_limit = os.getenv("SEMAPHORE_CONCURRENCY_LIMIT", concurrency_limit)
        self.semaphore = asyncio.Semaphore(concurrency_limit)

        # local_test: False => connect to production AI server
        self.local_test = local_test

        # granular: controls whether to use one client per score or one overall client
        # Currently not used, but left for future flexibility
        self.granular = granular

        # Set up logging (logs to both file and console)
        self.logger = DualLogger(
            log_dir="logs/processing", log_prefix="process_eval"
        ).get_logger()

    @staticmethod
    def parse_args():
        parser = argparse.ArgumentParser(
            description="Evaluate submissions and store in DB"
        )
        parser.add_argument(
            "--db-url",
            default="sqlite:///f1_fans_eval.db",
            help="SQLAlchemy DB URL, e.g. sqlite:///f1_fans_eval.db or postgresql://user:pass@host:port/db",
        )
        parser.add_argument(
            "--override",
            action="store_true",
            help="If set, will override existing evaluations and re-run them",
        )
        parser.add_argument(
            "--filter-source",
            default=None,
            help="Optional CSV/JSON/TXT file or JSON string with submission_ids to evaluate",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=2,
            help="Max number of concurrent evaluations",
        )
        parser.add_argument(
            "--local-test",
            action="store_true",
            help="Run in local test mode, skipping environment variable checks",
        )
        return parser.parse_args()

    @staticmethod
    def load_filter_ids(filter_source: str) -> Set[str]:
        """Load submission_ids from csv/json/txt or inline json string."""
        if not filter_source:
            return set()

        path = Path(filter_source)
        if path.exists():
            if path.suffix == ".csv":
                with open(path, newline="") as f:
                    reader = csv.DictReader(f)
                    if "sub_id" not in reader.fieldnames:
                        raise ValueError("CSV must contain 'sub_id' column.")
                    return {row["sub_id"] for row in reader}
            elif path.suffix == ".json":
                with open(path) as f:
                    data = json.load(f)
                    return set(map(str, data))
            else:  # TXT
                with open(path) as f:
                    return {line.strip() for line in f if line.strip()}
        else:
            try:
                data = json.loads(filter_source)
                if isinstance(data, list):
                    return set(map(str, data))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid filter_source: {filter_source}") from e
        return set()

    def build_score_clients(
        self, sub_id: str, prefix: str = "f1_fan_"
    ) -> Dict[str, Any]:
        """
        Create AI clients for each evaluation dimension.

        Args:
            sub_id: Submission ID (used for organizing log files)
            prefix: Prefix for agent names (default: "f1_fan_")

        Returns:
            Dictionary mapping score names to SimpleClient instances:
            {
                "knowledge": SimpleClient("f1_fan_knowledge"),
                "enthusiasm": SimpleClient("f1_fan_enthusiasm"),
                "humor": SimpleClient("f1_fan_humor")
            }

        Each client connects to a different AI agent that specializes in
        one scoring dimension. For example:
        - f1_fan_knowledge → evaluates F1 knowledge
        - f1_fan_enthusiasm → evaluates fan enthusiasm
        - f1_fan_humor → evaluates humor/entertainment value
        """
        # Get score fields (exclude brief_description, which is generated by agents)
        score_fields = [field for field in SCORE_FIELDS if field != "brief_description"]
        clients = {}

        for field in score_fields:
            # Build agent name (e.g., "f1_fan_knowledge")
            aname = f"{prefix}{field.replace('_score', '')}"

            # Create unique log directory for this submission+agent combo
            default_dir = f"{str(sub_id)[:7]}_{aname}"

            # Create client connected to this specific AI agent
            client = SimpleClient(
                agent_name=aname, default_dir=default_dir, local_test=self.local_test
            )
            clients[field] = client
        return clients

    async def _retry_eval(
        self, sub_id: str, client: SimpleClient, user_input: str, label: str
    ):
        """
        Call AI agent with automatic retry logic.

        Args:
            sub_id: Submission ID being evaluated
            client: SimpleClient connected to an AI agent
            user_input: Text to evaluate (F1 fan description)
            label: Which score dimension (e.g., "knowledge", "humor")

        Returns:
            Dictionary with evaluation results, or empty dict if all attempts fail

        This method:
        1. Creates a unique session ID for this attempt
        2. Calls the AI agent with a timeout
        3. If it fails, waits and retries (up to MAX_RETRIES times)
        4. Always cleans up the session after each attempt
        5. Returns parsed JSON response or empty dict on total failure
        """
        # Create a unique session root for this evaluation
        session_root = str(uuid.uuid4().hex[:16])

        # Try up to MAX_RETRIES times
        for attempt in range(1, MAX_RETRIES + 1):
            # Each attempt gets its own session ID
            current_session_id = f"{session_root}_{attempt}"

            try:
                self.logger.info("=" * 50)
                self.logger.info(
                    f"[{sub_id}] [{label}] Attempt {attempt} with session {current_session_id}"
                )

                # Call AI agent with timeout protection
                # asyncio.to_thread runs the blocking client call in a thread pool
                result_text = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.process_user_input, current_session_id, user_input
                    ),
                    timeout=int(os.getenv("ASYNC_WAITTIME_UNTIL_SERVER_RESPONDS", 600)),
                )

                # Parse response (might be string or already a dict)
                parsed = (
                    json.loads(result_text)
                    if isinstance(result_text, str)
                    else result_text
                )

                self.logger.info(f"[{sub_id}] [{label}] Success on attempt {attempt}")
                return parsed

            except Exception as e:
                # Log the error with full stack trace
                self.logger.error(
                    f"[{sub_id}] [{label}] Attempt {attempt} failed: {e}", exc_info=True
                )

                # Wait before retrying (unless this was the last attempt)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)

            finally:
                # Always clean up the session, even if there was an error
                try:
                    client.reset_session(current_session_id)
                except Exception as reset_err:
                    self.logger.warning(
                        f"[{sub_id}] [{label}] Reset failed after attempt {attempt}: {reset_err}"
                    )

        # If we get here, all attempts failed
        self.logger.error(
            f"[{session_root}] [{label}] All {MAX_RETRIES} attempts failed."
        )
        return {}  # Return empty dict to signal failure

    async def process_submission(self, sub: Tuple[str, str, str, str]):
        """
        Evaluate a single submission across all scoring dimensions.

        Args:
            sub: Tuple of (sub_id, email, description)

        Returns:
            Tuple of (sub_id, elapsed_time_seconds)

        This method orchestrates the full evaluation pipeline for one submission:
        1. Check if already evaluated (skip if yes, unless override=True)
        2. Create AI clients for each score dimension
        3. Call each AI agent to get knowledge/enthusiasm/humor scores
        4. Aggregate token metrics across all AI calls
        5. Store combined results in database
        6. Return timing info

        The semaphore ensures we don't overwhelm the AI server with too many
        concurrent requests.
        """
        sub_id, email, description = sub
        _ = email  # email is not used in processing currently (kept for future use)

        # Skip if already evaluated (unless override mode is enabled)
        if not self.override and self.db.evaluation_exists(sub_id):
            self.logger.info(f"⏩ Skipping {sub_id}, evaluation already exists.")
            return (sub_id, 0.0)

        start_time = time.perf_counter()
        results = {}

        # Use semaphore to limit concurrent AI calls (avoid overwhelming server)
        async with self.semaphore:
            # Create AI clients for each scoring dimension
            clients = self.build_score_clients(sub_id)

            # Initialize results structure
            results = {
                "evaluation": {},
                "token_accounting": {f: 0 for f in TOKEN_FIELDS},
            }

            # Collect brief descriptions from each agent
            brief_parts = []

            # Evaluate across all dimensions (knowledge, enthusiasm, humor)
            for field, client in clients.items():
                # Call AI agent with retry logic
                gresult = await self._retry_eval(sub_id, client, description, field)

                # Extract and store the score (0-100)
                score = gresult.get("evaluation", {}).get("score")
                if score is not None:
                    results["evaluation"][field] = score

                # Collect brief description from this dimension
                brief = gresult.get("evaluation", {}).get("brief_description")
                if brief:
                    brief_parts.append(f"{field}: {brief}")

                # Aggregate token metrics across all AI calls
                # (tracks total API usage and cost)
                token_data = gresult.get("token_accounting", {})
                for tk_field in TOKEN_FIELDS:
                    val = token_data.get(tk_field)
                    if isinstance(val, (int, float)):
                        results["token_accounting"][tk_field] += val

            # Combine brief descriptions from all dimensions
            results["evaluation"]["brief_description"] = "\n".join(brief_parts)

            # Calculate total elapsed time
            elapsed = time.perf_counter() - start_time

            # Store evaluation in database
            self.insert_to_db(sub_id=sub_id, response=results, elapsed=elapsed)
            self.logger.info(f"✅ Completed evaluation for {sub_id} in {elapsed:.2f}s")

            return (sub_id, elapsed)

    def insert_to_db(self, sub_id: str, response: Dict[str, Any], elapsed: float):
        """
        Store evaluation results in the database.

        Args:
            sub_id: Submission ID being evaluated
            response: Dictionary with "evaluation" (scores) and "token_accounting" (metrics)
            elapsed: Total processing time in seconds

        This method:
        1. Generates a unique evaluation ID
        2. Combines scores and token metrics into one record
        3. Retries on database errors (network issues, locks, etc.)
        4. Logs success/failure

        The evaluation record includes:
        - Scores (knowledge, enthusiasm, humor, brief_description)
        - Token metrics (total_tokens, cost, etc.)
        - Timing info (elapsed time)
        - Timestamp
        """
        # Generate unique evaluation ID (sub_id + random suffix)
        eval_id = f"{sub_id}_{uuid.uuid4().hex[:4]}"
        evaluated_at = datetime.now(timezone.utc)

        # Validate response
        if not response or not isinstance(response, dict):
            self.logger.warning(f"[{sub_id}] Empty or No response, skipping.")
            return

        # Build evaluation data record
        eval_data: Dict[str, Any] = {
            "total_processing_time_in_seconds": round(elapsed, 3),
            "evaluated_at": evaluated_at,
        }

        # Merge evaluation scores and token accounting into one flat dict
        complete_resp = {
            **response.get("evaluation", {}),
            **response.get("token_accounting", {}),
        }

        # Add all scores and token metrics to eval_data
        for f in SCORE_FIELDS + TOKEN_FIELDS:
            val = complete_resp.get(f)
            # Round floats to 3 decimal places for consistency
            if isinstance(val, float):
                val = round(val, 3)
            eval_data[f] = val

        # Try to store in database with retry logic (handles transient errors)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.db.insert_evaluation(eval_id, sub_id, eval_data)
                self.logger.info(f"✅ Stored evaluation for {sub_id}")
                break
            except Exception as e:
                self.logger.error(
                    f"❌ Insert failed for {sub_id} (attempt {attempt}): {e}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

    def get_submissions_to_process(self) -> List[Tuple[str, str, str, str]]:
        """
        Fetch submissions that need evaluation from the database.

        Returns:
            List of tuples: (sub_id, email, description)

        This method:
        1. Gets all submissions from database
        2. Applies filter if filter_ids was specified (only process certain IDs)
        3. Removes already-evaluated submissions (unless override=True)
        4. Returns the list of submissions to process

        Examples:
        - No filter, no override: Returns only submissions that haven't been evaluated yet
        - With filter: Returns only matching submission IDs
        - With override: Returns all submissions (even if already evaluated)
        """
        # Fetch all submissions from database
        all_subs = [
            (s.sub_id, s.email, s.description) for s in self.db.get_all_submissions()
        ]

        # Apply filter if specified (e.g., only process certain submission IDs)
        if self.filter_ids:
            all_subs = [s for s in all_subs if s[0] in self.filter_ids]
            self.logger.info(
                f"Filter applied. {len(all_subs)} submissions match filter."
            )

        # Remove already-evaluated submissions (unless override mode is on)
        if not self.override:
            pending = [s for s in all_subs if not self.db.evaluation_exists(s[0])]
            self.logger.info(f"Found {len(pending)} submissions pending evaluation.")
            return pending

        # Override mode: re-evaluate everything
        self.logger.info(
            f"Override enabled: evaluating all {len(all_subs)} submissions."
        )
        return all_subs

    async def run(self):
        """
        Main entry point - run the full evaluation pipeline.

        This method:
        1. Fetches submissions that need evaluation
        2. Creates async tasks for each submission
        3. Runs all evaluations in parallel (with concurrency limit from semaphore)
        4. Collects results and timing metrics
        5. Prints summary statistics
        6. Closes database connection

        To use:
            processor = ProcessEvaluation()
            asyncio.run(processor.run())
        """
        # Get list of submissions to evaluate
        subs = self.get_submissions_to_process()
        if not subs:
            self.logger.info("✅ Nothing to evaluate.")
            return

        self.logger.info(f"Starting evaluation of {len(subs)} submissions...")
        start_all = time.perf_counter()
        processed_times: List[float] = []

        try:
            # Create async task for each submission
            tasks = [self.process_submission(sub) for sub in subs]

            # Run all tasks concurrently (asyncio.gather waits for all to complete)
            # The semaphore inside process_submission limits actual concurrency
            results = await asyncio.gather(*tasks)

            # Collect timing results
            for sub_id, elapsed in results:
                if elapsed > 0:  # Skip submissions that were skipped
                    processed_times.append(elapsed)
                    self.logger.info(f"[Report] {sub_id} processed in {elapsed:.2f}s")

            # Calculate and log summary statistics
            total_time = time.perf_counter() - start_all
            avg_time = (
                sum(processed_times) / len(processed_times) if processed_times else 0.0
            )
            self.logger.info("========== Evaluation Summary ==========")
            self.logger.info(f"Total processed: {len(processed_times)}")
            self.logger.info(f"Average time per submission: {avg_time:.2f}s")
            self.logger.info(f"Total time: {total_time:.2f}s")
        finally:
            # Always close database connection, even if there was an error
            self.db.close()
            self.logger.info("Database connection closed.")


if __name__ == "__main__":
    args = ProcessEvaluation.parse_args()
    filter_ids = (
        ProcessEvaluation.load_filter_ids(args.filter_source)
        if args.filter_source
        else set()
    )

    processor = ProcessEvaluation(
        db_url=args.db_url,
        override=args.override,
        filter_ids=filter_ids,
        concurrency_limit=args.concurrency,
        local_test=args.local_test,
    )
    asyncio.run(processor.run())
