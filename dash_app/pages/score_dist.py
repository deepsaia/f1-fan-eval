# dash_app/pages/score_distribution.py
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from dash_app.utils.chart_helper import make_boxplots, make_histograms
from dash_app.utils.data_helpers import (
    get_data_dict,
    get_date_range_utc_to_current_geo_tz,
    make_dataframes,
)
from dash_app.utils.layout_helper import make_dashboard_layout

dash.register_page(__name__, path="/score-distribution", name="📈 Score Distribution")

# Define score-related fields
SCORE_FIELDS = ["knowledge", "enthusiasm", "humor"]

layout = make_dashboard_layout(
    title="📈 Score Distribution Analysis",
    refresh_id="refresh-dist-btn",
    cache_id="score-dist-cache",
    counters=[
        ("dist-submissions-count", "Submissions"),
        ("dist-evaluations-count", "Evaluations"),
    ],
    controls=[
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("📊 Metrics"),
                        dcc.Dropdown(
                            id="score-select",
                            options=[
                                {"label": s.capitalize(), "value": s}
                                for s in SCORE_FIELDS
                            ],
                            value=SCORE_FIELDS,
                            multi=True,
                        ),
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        html.Label("📅 Date Range"),
                        dcc.DatePickerRange(
                            id="dist-date-range", display_format="YYYY-MM-DD"
                        ),
                    ],
                    width=4,
                ),
            ],
            className="mb-3",
        ),
        html.Div(id="score-summary"),
    ],
    graphs=["score-histograms", "score-boxplots"],
)


# ------------------------------------------------------------
# 1️⃣ Load & cache data
# ------------------------------------------------------------
@dash.callback(
    Output("score-dist-cache", "data"),
    Input("refresh-dist-btn", "n_clicks"),
    prevent_initial_call=False,
)
def load_data_cb(n_clicks):
    return get_data_dict()


# ------------------------------------------------------------
# 2️⃣ Update date range dynamically
# ------------------------------------------------------------
@dash.callback(
    [Output("dist-date-range", "start_date"), Output("dist-date-range", "end_date")],
    Input("score-dist-cache", "data"),
)
def update_date_range(data):
    if not data:
        return None, None

    df_eval, df_sub = make_dataframes(data)

    # Get date range: min from submissions.processed_at, max from evaluations.evaluated_at
    # Convert from UTC to current geographic timezone (fallback: Pacific)
    min_date, max_date = get_date_range_utc_to_current_geo_tz(df_sub, df_eval)

    return min_date, max_date


# ------------------------------------------------------------
# 3️⃣ Render summary + charts
# ------------------------------------------------------------
@dash.callback(
    [
        Output("dist-submissions-count", "children"),
        Output("dist-evaluations-count", "children"),
        Output("score-summary", "children"),
        Output("score-histograms", "figure"),
        Output("score-boxplots", "figure"),
    ],
    [
        Input("score-dist-cache", "data"),
        Input("score-select", "value"),
        Input("dist-date-range", "start_date"),
        Input("dist-date-range", "end_date"),
    ],
    memoize=True,  # cache results for same inputs
)
def render_score_distribution(data, selected_scores, start_date, end_date):
    if not data:
        return (
            "Submissions: 0",
            "Evaluations: 0",
            html.P("No data."),
            go.Figure(),
            go.Figure(),
        )

    df_eval, df_sub = make_dataframes(data)

    if df_eval.empty:
        return (
            "Submissions: 0",
            "Evaluations: 0",
            html.P("No evaluation data."),
            go.Figure(),
            go.Figure(),
        )

    # Filter by date range
    if start_date and end_date and "evaluated_at" in df_eval.columns:
        mask = (
            pd.to_datetime(df_eval["evaluated_at"]) >= pd.to_datetime(start_date)
        ) & (pd.to_datetime(df_eval["evaluated_at"]) <= pd.to_datetime(end_date))
        df_eval = df_eval[mask]

    sub_count = len(df_sub)
    eval_count = len(df_eval)

    # Calculate average score from the three base scores
    if all(score in df_eval.columns for score in SCORE_FIELDS):
        df_eval["average"] = df_eval[SCORE_FIELDS].mean(axis=1)

    # Add average to selected scores if base scores are selected
    scores_to_plot = selected_scores.copy() if selected_scores else []
    if scores_to_plot and "average" in df_eval.columns:
        scores_to_plot.append("average")

    # Summary stats
    mean_scores = df_eval[selected_scores].mean().mean() if selected_scores else 0
    std_scores = df_eval[selected_scores].std().mean() if selected_scores else 0
    summary = dbc.Row(
        [
            dbc.Col(html.Div(f"📄 Total Submissions: {sub_count}")),
            dbc.Col(html.Div(f"🧾 Evaluations: {eval_count}")),
            dbc.Col(html.Div(f"📈 Mean Score: {mean_scores:.2f}")),
            dbc.Col(html.Div(f"📊 Std Dev: {std_scores:.2f}")),
        ],
        className="mb-3",
    )

    # ---- Histograms ----
    if scores_to_plot:
        fig_hist = make_histograms(
            df_eval, scores_to_plot, title="Score Distribution (including Average)"
        )
        fig_box = make_boxplots(
            df_eval, scores_to_plot, title="Score Distribution (including Average)"
        )
    else:
        fig_hist = go.Figure()
        fig_box = go.Figure()

    return (
        f"Submissions: {sub_count}",
        f"Evaluations: {eval_count}",
        summary,
        fig_hist,
        fig_box,
    )
