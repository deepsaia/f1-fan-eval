from datetime import datetime, timedelta

import pandas as pd

from dash_app.db.eval_data_loader import get_loader

_loader = get_loader()


def get_data_dict():
    """Unified data loading and conversion to serializable dict."""
    df_eval, df_sub, df_fs = _loader.load_all_data()
    return {"eval": df_eval.to_dict("records"), "sub": df_sub.to_dict("records")}


def make_dataframes(data: dict):
    """Convert dicts from dcc.Store back to pandas DataFrames."""
    if not data:
        return pd.DataFrame(), pd.DataFrame()
    return pd.DataFrame(data.get("eval", [])), pd.DataFrame(data.get("sub", []))


def get_current_timezone():
    """
    Detect the current geographic timezone.

    Returns:
        str: Timezone name (e.g., 'America/Los_Angeles'), defaults to 'America/Los_Angeles' (PDT) if detection fails
    """
    try:
        now = datetime.now().astimezone()
        current_tz = now.tzname()

        # Map common timezone abbreviations to IANA timezone names
        tz_mapping = {
            "PDT": "America/Los_Angeles",
            "PST": "America/Los_Angeles",
            "EDT": "America/New_York",
            "EST": "America/New_York",
            "CDT": "America/Chicago",
            "CST": "America/Chicago",
            "MDT": "America/Denver",
            "MST": "America/Denver",
            "UTC": "UTC",
        }

        # Try to get IANA timezone name from tzinfo
        if hasattr(now.tzinfo, "zone") and now.tzinfo.zone:
            return now.tzinfo.zone

        # Fall back to mapping from abbreviation
        if current_tz in tz_mapping:
            return tz_mapping[current_tz]

        # If we can't determine, default to Pacific
        return "America/Los_Angeles"
    except Exception:
        # Fallback to Pacific timezone if detection fails
        return "America/Los_Angeles"


def get_date_range_utc_to_current_geo_tz(df_sub: pd.DataFrame, df_eval: pd.DataFrame):
    """
    Calculate date range from submissions and evaluations with timezone conversion.

    - Min date: From submissions.processed_at (earliest submission)
    - Max date: From evaluations.evaluated_at (latest evaluation)
    - Convert from UTC (stored in DB) to current geographic timezone
    - Fallback to Pacific timezone (PDT/PST) if timezone detection fails

    Returns:
        tuple: (min_date, max_date) as date objects in current timezone, or (None, None) if data unavailable
    """
    min_date, max_date = None, None

    # Detect current timezone
    target_tz = get_current_timezone()

    # Get min date from submissions.processed_at
    if not df_sub.empty and "processed_at" in df_sub.columns:
        df_sub_copy = df_sub.copy()
        df_sub_copy["processed_at"] = pd.to_datetime(
            df_sub_copy["processed_at"], errors="coerce", utc=True
        )
        if not df_sub_copy["processed_at"].isna().all():
            min_dt = df_sub_copy["processed_at"].min()
            # Convert UTC to current timezone
            min_date = min_dt.tz_convert(target_tz).date() - timedelta(
                days=1
            )  # Include full day

    # Get max date from evaluations.evaluated_at
    if not df_eval.empty and "evaluated_at" in df_eval.columns:
        df_eval_copy = df_eval.copy()
        df_eval_copy["evaluated_at"] = pd.to_datetime(
            df_eval_copy["evaluated_at"], errors="coerce", utc=True
        )
        if not df_eval_copy["evaluated_at"].isna().all():
            max_dt = df_eval_copy["evaluated_at"].max()
            # Convert UTC to current timezone
            max_date = max_dt.tz_convert(target_tz).date() + timedelta(
                days=1
            )  # Include full day

    return min_date, max_date


def data_not_available():
    """Standard placeholder for empty datasets."""
    return ["No data."] * 6
