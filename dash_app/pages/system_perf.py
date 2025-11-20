import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from dash_app.utils.chart_helper import make_boxplots, make_histograms, make_time_series
from dash_app.utils.data_helpers import (
    get_data_dict,
    get_date_range_utc_to_current_geo_tz,
    make_dataframes,
)
from dash_app.utils.layout_helper import make_dashboard_layout

dash.register_page(__name__, path="/system-performance", name="⚙️ System Performance")

# ---------------------------------------------
# Define performance-related fields
# ---------------------------------------------
PERF_FIELDS = [
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "successful_requests",
    "total_cost",
    "time_taken_in_seconds",
    "total_processing_time_in_seconds",
]

# ---------------------------------------------
# Layout
# ---------------------------------------------
layout = make_dashboard_layout(
    title="⚙️ System Performance Analysis",
    refresh_id="perf-refresh-btn",
    cache_id="perf-cache",
    counters=[
        ("perf-submissions-count", "Submissions"),
        ("perf-evaluations-count", "Evaluations"),
    ],
    controls=[
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("📅 Date Range"),
                        dcc.DatePickerRange(
                            id="perf-date-range", display_format="YYYY-MM-DD"
                        ),
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        html.Label("📊 Performance Metrics"),
                        dcc.Dropdown(
                            id="perf-metric-select",
                            options=[
                                {"label": f"{s.replace('_', ' ').title()}", "value": s}
                                for s in PERF_FIELDS
                            ],
                            value=[
                                "total_cost",
                                "total_tokens",
                                "time_taken_in_seconds",
                            ],
                            multi=True,
                        ),
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        html.Label("📈 Average Metrics"),
                        dcc.Checklist(
                            id="perf-avg-select",
                            options=[
                                {
                                    "label": f"Avg {s.replace('_', ' ').title()}",
                                    "value": f"avg_{s}",
                                }
                                for s in PERF_FIELDS
                            ],
                            value=[
                                "avg_total_cost",
                                "avg_total_tokens",
                                "avg_time_taken_in_seconds",
                            ],
                            inline=True,
                        ),
                    ],
                    width=4,
                ),
            ]
        ),
    ],
    graphs=[
        "perf-histograms",
        "perf-boxplots",
        "perf-timeseries",
        "perf-summary-table",
    ],
)


# ---------------------------------------------
# 1️⃣ Load & cache data
# ---------------------------------------------
@dash.callback(
    Output("perf-cache", "data"),
    Input("perf-refresh-btn", "n_clicks"),
    prevent_initial_call=False,
)
def load_perf_data(n_clicks):
    """Fetch and cache data once."""
    return get_data_dict()


# ---------------------------------------------
# 2️⃣ Populate dynamic date range
# ---------------------------------------------
@dash.callback(
    [Output("perf-date-range", "start_date"), Output("perf-date-range", "end_date")],
    Input("perf-cache", "data"),
)
def update_date_range(data):
    if not data:
        return None, None

    df_eval, df_sub = make_dataframes(data)

    # Get date range: min from submissions.processed_at, max from evaluations.evaluated_at
    # Convert from UTC to current geographic timezone (fallback: Pacific)
    min_date, max_date = get_date_range_utc_to_current_geo_tz(df_sub, df_eval)

    return min_date, max_date


# ---------------------------------------------
# 3️⃣ Render performance analytics
# ---------------------------------------------
@dash.callback(
    [
        Output("perf-submissions-count", "children"),
        Output("perf-evaluations-count", "children"),
        Output("perf-histograms", "figure"),
        Output("perf-boxplots", "figure"),
        Output("perf-timeseries", "figure"),
        Output("perf-summary-table", "children"),
    ],
    [
        Input("perf-cache", "data"),
        Input("perf-metric-select", "value"),
        Input("perf-avg-select", "value"),
        Input("perf-date-range", "start_date"),
        Input("perf-date-range", "end_date"),
    ],
)
def render_perf_dashboard(data, metrics, avg_metrics, start_date, end_date):
    """Main performance visualization logic."""
    if not data:
        return (
            "Submissions: 0",
            "Evaluations: 0",
            go.Figure(),
            go.Figure(),
            go.Figure(),
            html.P("No data available."),
        )

    df_eval, df_sub = make_dataframes(data)
    if df_eval.empty:
        return (
            "Submissions: 0",
            "Evaluations: 0",
            go.Figure(),
            go.Figure(),
            go.Figure(),
            html.P("No evaluation data."),
        )

    # --- Filter by date range ---
    if start_date and end_date and "evaluated_at" in df_eval.columns:
        mask = (
            pd.to_datetime(df_eval["evaluated_at"]) >= pd.to_datetime(start_date)
        ) & (pd.to_datetime(df_eval["evaluated_at"]) <= pd.to_datetime(end_date))
        df_eval = df_eval[mask]

    sub_count = len(df_sub)
    eval_count = len(df_eval)

    # --- Compute average metrics per submission ---
    avg_df = df_eval.groupby("sub_id")[metrics].mean().add_prefix("avg_").reset_index()
    merged_df = pd.merge(
        df_eval.groupby("sub_id")[metrics].mean().reset_index(), avg_df, on="sub_id"
    )

    # --- Selected metrics ---
    selected_metrics = metrics + avg_metrics
    selected_metrics = [m for m in selected_metrics if m in merged_df.columns]

    # ---- Histograms ----
    fig_hist = make_histograms(
        df=merged_df, columns=selected_metrics, title="Performance Metric Distributions"
    )

    # ---- Box Plots ----
    fig_box = make_boxplots(
        merged_df, selected_metrics, title="Performance Metric Distribution"
    )

    # ---- Time Series ----
    fig_time = make_time_series(
        df_eval, metrics, avg_metrics, title="📈 Performance Trends Over Time"
    )

    # ---- Summary Table ----
    comp_df = merged_df.set_index("sub_id")[selected_metrics].copy()
    comp_df["total"] = comp_df.sum(axis=1)
    comp_df["overall_avg"] = comp_df[selected_metrics].mean(axis=1)

    table = dbc.Table.from_dataframe(
        comp_df.round(3).reset_index(),
        striped=True,
        bordered=True,
        hover=True,
    )

    return (
        f"Submissions: {sub_count}",
        f"Evaluations: {eval_count}",
        fig_hist,
        fig_box,
        fig_time,
        table,
    )
