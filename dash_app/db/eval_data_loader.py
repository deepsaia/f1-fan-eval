import weakref
from functools import lru_cache, wraps

import pandas as pd
from sqlalchemy.inspection import inspect

from db.eval_database import (  # adjust import path if needed
    EvalDatabase,  # your ORM wrapper
    Evaluation,
    Submission,
)


def safe_lru_cache(maxsize=128):
    """
    A safer variant of functools.lru_cache for instance methods.

    It wraps the function so that `self` is held as a weak reference,
    preventing memory leaks if instances are destroyed while the cache persists.
    """

    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            # hold a weak reference to the instance (self)
            self_ref = weakref.ref(self)

            # define a cache specific to this instance
            @lru_cache(maxsize=maxsize)
            def cached_call(*args, **kwargs):
                inst = self_ref()
                if inst is None:
                    # instance was garbage collected
                    return None
                return method(inst, *args, **kwargs)

            # store the per-instance cache so each instance has its own
            cache_name = f"__cached_{method.__name__}"
            if not hasattr(self, cache_name):
                setattr(self, cache_name, cached_call)

            return getattr(self, cache_name)(*args, **kwargs)

        return wrapper

    return decorator


class EvalDataLoader:
    """
    High-performance data loader for F1-Fan-Eval dashboards.
    - Auto-infers expected schema columns from SQLAlchemy models
    - Ensures consistent DataFrame structures
    - Includes lightweight in-memory caching (via LRU)
    """

    def __init__(self, db_url: str = None, cache_size: int = 8):
        self.db = EvalDatabase(db_url)
        self.submission_cols = self._infer_columns(Submission)
        self.evaluation_cols = self._infer_columns(Evaluation)
        self.cache_size = cache_size

    # ----------------------------------------------------
    # 🔍 Introspection helpers
    # ----------------------------------------------------
    def _infer_columns(self, model_cls):
        """Introspect SQLAlchemy model columns as a list of strings."""
        try:
            mapper = inspect(model_cls)
            return [c.key for c in mapper.columns]
        except Exception as e:
            print(
                f"[EvalDataLoader] Warning: Could not infer columns for {model_cls.__name__}: {e}"
            )
            return []

    # ----------------------------------------------------
    # 🧠 Core data loading methods
    # ----------------------------------------------------
    @safe_lru_cache(maxsize=8)
    def get_evaluations_df(self, limit: int | None = None):
        """Load evaluations as a Pandas DataFrame, ensure schema integrity."""
        try:
            df = self.db.get_all_evaluations_as_df()
        except Exception as e:
            print(f"[EvalDataLoader] Error fetching evaluations: {e}")
            df = pd.DataFrame()

        # Guarantee schema consistency
        df = self._ensure_columns(df, self.evaluation_cols)

        # Convert timestamps safely
        if "evaluated_at" in df.columns:
            df["evaluated_at"] = pd.to_datetime(df["evaluated_at"], errors="coerce")

        return df

    @safe_lru_cache(maxsize=8)
    def get_submissions_df(self, limit: int | None = None):
        """Load submissions as a Pandas DataFrame, ensure schema integrity."""
        try:
            df = self.db.get_all_submissions_as_df()
        except Exception as e:
            print(f"[EvalDataLoader] Error fetching submissions: {e}")
            df = pd.DataFrame()

        df = self._ensure_columns(df, self.submission_cols)

        if "processed_at" in df.columns:
            df["processed_at"] = pd.to_datetime(df["processed_at"], errors="coerce")

        return df

    @safe_lru_cache(maxsize=4)
    def get_inputs_df(self, limit: int | None = None):
        """Load inputs (FileStatus table) if available."""
        try:
            df = self.db.get_all_inputs_as_df()
        except Exception:
            df = pd.DataFrame()
        return df

    # ----------------------------------------------------
    # 🔄 Convenience
    # ----------------------------------------------------
    def load_all_data(self, limit: int | None = None):
        """Unified loader for all three tables."""
        df_eval = self.get_evaluations_df(limit)
        df_sub = self.get_submissions_df(limit)
        df_fs = self.get_inputs_df(limit)
        return df_eval, df_sub, df_fs

    def _ensure_columns(self, df: pd.DataFrame, expected_cols: list[str]):
        """Add any missing columns and enforce correct column order."""
        if df.empty:
            return pd.DataFrame(columns=expected_cols)
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None
        return df[expected_cols]

    # ----------------------------------------------------
    # 🧹 Cache management
    # ----------------------------------------------------
    def clear_cache(self):
        """Clear cached DataFrames."""
        self.get_evaluations_df.cache_clear()
        self.get_submissions_df.cache_clear()
        self.get_inputs_df.cache_clear()
        print("[EvalDataLoader] Cache cleared.")

    def close(self):
        """Close DB connection safely."""
        try:
            self.db.close()
        except Exception:
            pass


# ----------------------------------------------------
# ✅ Global access helper
# ----------------------------------------------------
_loader_instance: EvalDataLoader | None = None


def get_loader(db_url: str = None) -> EvalDataLoader:
    """Return a shared EvalDataLoader instance (singleton style)."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = EvalDataLoader(db_url=db_url)
    return _loader_instance
