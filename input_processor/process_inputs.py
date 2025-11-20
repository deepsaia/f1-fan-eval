"""
Process Inputs - CSV/JSON ingestion for F1 fan submissions.

This module reads raw input files (typically from surveys or forms) and
loads them into the database as Submission records.

Key features:
- Automatic character encoding detection (handles international characters)
- CSV parsing with proper column mapping
- Duplicate detection (skip already-processed submissions)
- Batch processing of multiple submissions
"""

import argparse
import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import chardet

from db.eval_database import EvalDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# CSV column names from the input file
# These must match exactly what's in the source CSV
SUB_ID = "Respondent ID"
EMAIL = "Please share your email address so we can contact you if you win"
DESCRIPTION = "In a few lines tell us why you believe you are the biggest F1 fan."


class ProcessInputs:
    """
    CSV ingestion processor for F1 fan submissions.

    This class:
    - Reads CSV files with submission data
    - Detects file encoding automatically
    - Extracts relevant fields (ID, email, description)
    - Stores submissions in the database
    - Skips duplicates (unless override mode is enabled)

    Usage:
        processor = ProcessInputs()
        processor.process_all()
    """

    def __init__(self):
        """
        Initialize the input processor.

        Parses command-line arguments and sets up:
        - Database connection
        - Input file path
        - Override mode (re-process existing submissions if True)
        """
        self.args = self.parse_args()
        self.db = EvalDatabase(use_sqlite=self.args.get("use_sqlite"))
        self.input_source = self.args.get("input_source")
        self.override = self.args.get("override", False)
        self.logger = logging.getLogger("ProcessInputs")

    @staticmethod
    def parse_args():
        parser = argparse.ArgumentParser(
            description="Process F1 Fan submissions and store in DB"
        )
        parser.add_argument(
            "--input-source",
            default="samples/f1_sample.csv",
            help="Path to input CSV file",
        )
        parser.add_argument(
            "--override",
            action="store_true",
            help="Re-insert even if submission already exists",
        )
        parser.add_argument(
            "--use-sqlite", action="store_true", help="Use local SQLite database"
        )
        args, _ = parser.parse_known_args()
        return vars(args)

    def detect_encoding(self, path):
        """
        Automatically detect the character encoding of a file.

        Args:
            path: Path to the file

        Returns:
            String encoding name (e.g., "utf-8", "latin-1", "iso-8859-1")

        This is important because CSV files from different sources may use
        different character encodings, especially for international text.
        The chardet library samples the first 10KB to make an educated guess.
        """
        with open(path, "rb") as f:
            raw = f.read(10000)  # Read first 10KB as bytes

        result = chardet.detect(raw)
        enc = result.get("encoding")

        if enc:
            enc = enc.strip()
            self.logger.info(
                "🔍 Detected encoding: %s (confidence: %.2f)",
                enc,
                result.get("confidence", 0.0),
            )
            return enc

        # Fallback if detection fails
        self.logger.warning("⚠️ Encoding detection failed, defaulting to latin-1.")
        return "latin-1"

    def load_input(self, source: str):
        """
        Load and parse CSV file containing submissions.

        Args:
            source: Path to CSV file

        Returns:
            List of dictionaries, each containing:
            - sub_id: Submission ID
            - email: User email
            - description: Why they're an F1 fan

        This method:
        1. Detects file encoding
        2. Parses CSV using Python's csv.DictReader
        3. Extracts relevant columns
        4. Filters out incomplete rows (missing required fields)
        5. Strips whitespace from all values
        """
        path_obj = Path(source)
        if not path_obj.exists():
            raise FileNotFoundError(f"Input file not found: {source}")

        # Detect encoding first (handles international characters)
        enc = self.detect_encoding(path_obj)

        submissions = []
        with open(path_obj, newline="", encoding=enc) as f:
            reader = csv.DictReader(f)  # Treats first row as column headers

            for row in reader:
                # Extract the three key fields
                sub_id = row.get(SUB_ID)
                email = row.get(EMAIL)
                description = row.get(DESCRIPTION)

                # Only include rows with all required fields
                if sub_id and email and description:
                    submissions.append(
                        {
                            "sub_id": str(sub_id).strip(),
                            "email": email.strip(),
                            "description": description.strip(),
                        }
                    )

        self.logger.info(f"📦 Loaded {len(submissions)} submissions from {source}")
        return submissions

    def process_one_submission(self, submission):
        """
        Insert a single submission into the database.

        Args:
            submission: Dictionary with sub_id, email, description

        This method:
        1. Checks if submission already exists
        2. Skips if it does (unless override mode is enabled)
        3. Inserts into database with timestamp
        4. Logs success or failure
        """
        start_time = time.perf_counter()
        sub_id = submission["sub_id"]
        email = submission["email"]
        description = submission["description"]

        # Skip if already in database (unless override mode)
        if not self.override and self.db.submission_exists(sub_id):
            self.logger.info(f"⏩ Skipping {sub_id} — already exists.")
            return

        elapsed = time.perf_counter() - start_time

        # Insert into database
        success = self.db.insert_submission(
            sub_id=sub_id,
            email=email,
            description=description,
            processed_at=datetime.now(timezone.utc),
            total_processing_time_in_seconds=round(elapsed, 3),
        )

        if success:
            self.logger.info(f"✅ Inserted submission {sub_id} ({email})")
        else:
            self.logger.error(f"❌ Failed to insert submission {sub_id}")

    def process_all(self):
        """
        Main entry point - load and process all submissions from the input file.

        This method:
        1. Loads submissions from CSV
        2. Processes each one sequentially
        3. Logs completion message

        To use:
            processor = ProcessInputs()
            processor.process_all()
        """
        submissions = self.load_input(self.input_source)

        for sub in submissions:
            self.process_one_submission(sub)

        self.logger.info("🎯 All submissions processed successfully.")


if __name__ == "__main__":
    processor = ProcessInputs()
    processor.process_all()
