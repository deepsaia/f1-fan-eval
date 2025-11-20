"""
Database Utilities - Helper functions for database connection management.

This module provides utilities for:
- Building database connection URLs
- Testing database connectivity
- Switching between SQLite (local dev) and PostgreSQL (production)
- Loading database configuration from environment variables

The DBUtils class handles connection fallback:
1. Try PostgreSQL if credentials are configured
2. Fall back to SQLite if PostgreSQL fails
"""

import logging
import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DBUtils:
    """
    Database utility class for connection management and URL building.

    This class helps manage database connections with automatic fallback
    from PostgreSQL to SQLite if needed.
    """

    def __init__(self, use_sqlite: bool = False):
        """
        Initialize DBUtils.

        Args:
            use_sqlite: If True, always use SQLite (skip PostgreSQL)
        """
        self.db_url = None
        self.use_sqlite = use_sqlite

    def load_env_variables(self):
        """
        Load environment variables from .env file.

        Reads database connection parameters:
        - POSTGRES_USERNAME
        - POSTGRES_PASSWORD
        - POSTGRES_HOST
        - POSTGRES_PORT
        - DBNAME
        - POSTGRES_USE_SSL
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
            logger.warning(
                f"No .env file found at {env_file}. Using default environment variables."
            )

    def test_connection(self, db_url: str) -> bool:
        """
        Test database connectivity.

        Args:
            db_url: SQLAlchemy connection string

        Returns:
            True if connection successful, False otherwise

        This creates a temporary engine and tries a simple SELECT 1 query
        to verify the database is reachable and credentials are valid.
        """
        try:
            engine = create_engine(db_url)
            with engine.connect() as conn:
                # Execute simple query to test connection
                conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful.")
            return True
        except SQLAlchemyError as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            return False

    def build_db_url(self) -> str:
        """
        Build database connection URL with automatic fallback.

        Returns:
            SQLAlchemy connection string

        Logic:
        1. If use_sqlite=True, return SQLite URL immediately
        2. Otherwise, try to build PostgreSQL URL from environment
        3. Test PostgreSQL connection
        4. Fall back to SQLite if PostgreSQL fails

        This ensures the app always has a working database, even if
        PostgreSQL is misconfigured.
        """
        # Default SQLite fallback
        default_url = "sqlite:///vibe_coding_eval.db"

        # Use SQLite if explicitly requested
        if self.use_sqlite:
            logger.info("🔌 Using default SQLite database.")
            return default_url

        # Load environment configuration
        self.load_env_variables()

        # Build PostgreSQL URL from environment
        use_ssl = os.getenv("POSTGRES_USE_SSL", "false").lower() == "true"
        username = quote_plus(os.getenv("POSTGRES_USERNAME", "postgres"))
        pwd = os.getenv("POSTGRES_PASSWORD", "")
        host = os.getenv("POSTGRES_HOST", "localhost")
        db = os.getenv("DBNAME", "vibe-coding-db")
        port = os.getenv("POSTGRES_PORT", "5432")

        try:
            # URL-encode password (handles special characters)
            encoded_pwd = quote_plus(pwd)

            # Add SSL suffix if enabled
            ssl_suffix = "?sslmode=require" if use_ssl else ""

            # Build full PostgreSQL connection string
            db_url = f"postgresql+psycopg2://{username}:{encoded_pwd}@{host}:{port}/{db}{ssl_suffix}"

            logger.info(
                f"🔌 Using PostgreSQL DB at {host}:{port}/{db}{' with SSL' if use_ssl else ''}"
            )

            # Test connection before returning
            if self.test_connection(db_url):
                return db_url
            else:
                # Connection failed, fall back to SQLite
                logger.warning(
                    "⚠️ Falling back to SQLite after failed Postgres connection."
                )
                return default_url

        except Exception as e:
            # Error building URL, fall back to SQLite
            logger.warning(
                f"⚠️ Failed to build PostgreSQL DB URL. Falling back to SQLite. Error: {e}"
            )
            logger.info(f"[DEBUG] Final DB URL: {default_url}")
            return default_url


if __name__ == "__main__":
    dbutils = DBUtils()
    dbutils.db_url = dbutils.build_db_url()
    print(f"DB URL: {dbutils.db_url}")
