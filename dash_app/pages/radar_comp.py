from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html

from dash_app.utils.chart_helper import make_radar_chart
from dash_app.utils.data_helpers import (
    get_data_dict,
    get_date_range_utc_to_current_geo_tz,
    make_dataframes,
)
from dash_app.utils.layout_helper import make_dashboard_layout
from dash_app.utils.ui_helpers import make_table

dash.register_page(__name__, path="/radar-comparison", name="🎯 Radar Comparison")

SCORE_FIELDS = ["knowledge", "enthusiasm", "humor"]

# ------------------------------------------------------------
# Layout
# ------------------------------------------------------------
layout = html.Div(
    [
        dcc.Download(id="download-comparison-csv"),
        dcc.Store(id="comparison-data-store"),
        make_dashboard_layout(
            title="🎯 Radar Comparison Analysis",
            refresh_id="refresh-radar-btn",
            cache_id="radar-cache",
            counters=[
                ("radar-submissions-count", "Submissions"),
                ("radar-evaluations-count", "Evaluations"),
            ],
            controls=[
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("📝 Submissions"),
                                dcc.Dropdown(
                                    id="radar-submission-select",
                                    multi=True,
                                    placeholder="Select submissions...",
                                ),
                            ],
                            width=4,
                        ),
                        dbc.Col(
                            [
                                html.Label("📅 Date Range"),
                                dcc.DatePickerRange(
                                    id="radar-date-range", display_format="YYYY-MM-DD"
                                ),
                            ],
                            width=4,
                        ),
                    ],
                    className="mb-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("📊 Score Metrics"),
                                dcc.Dropdown(
                                    id="radar-score-select",
                                    options=[
                                        {"label": s.capitalize(), "value": s}
                                        for s in SCORE_FIELDS
                                    ],
                                    value=SCORE_FIELDS,
                                    multi=True,
                                ),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Label("📈 Average Scores"),
                                dcc.Checklist(
                                    id="radar-avg-score-select",
                                    options=[
                                        {
                                            "label": f"Avg {s.capitalize()}",
                                            "value": f"avg_{s}",
                                        }
                                        for s in SCORE_FIELDS
                                    ],
                                    value=[f"avg_{s}" for s in SCORE_FIELDS],
                                    inline=True,
                                ),
                            ],
                            width=6,
                        ),
                    ]
                ),
            ],
            graphs=["radar-chart"],
            sections=[("📊 Side-by-Side Comparison", "comparison-table-section")],
        ),
    ]
)


# ------------------------------------------------------------
# 1️⃣ Load & cache data
# ------------------------------------------------------------
@dash.callback(
    Output("radar-cache", "data"),
    Input("refresh-radar-btn", "n_clicks"),
    prevent_initial_call=False,
)
def load_radar_data(n_clicks):
    """Fetch and cache all relevant data."""
    return get_data_dict()


# ------------------------------------------------------------
# 2️⃣ Populate dynamic dropdowns and date ranges
# ------------------------------------------------------------
@dash.callback(
    [
        Output("radar-submission-select", "options"),
        Output("radar-submission-select", "value"),
        Output("radar-date-range", "start_date"),
        Output("radar-date-range", "end_date"),
    ],
    Input("radar-cache", "data"),
)
def populate_options(data):
    if not data:
        return [], [], None, None

    df_eval, df_sub = make_dataframes(data)
    if df_eval.empty:
        return [], [], None, None

    submissions = sorted(df_eval["sub_id"].unique())
    options = [{"label": str(s), "value": s} for s in submissions]
    default_vals = submissions[:5] if len(submissions) >= 5 else submissions

    # Get date range: min from submissions.processed_at, max from evaluations.evaluated_at
    # Convert from UTC to current geographic timezone (fallback: Pacific)
    min_date, max_date = get_date_range_utc_to_current_geo_tz(df_sub, df_eval)

    return options, default_vals, min_date, max_date


# ------------------------------------------------------------
# 3️⃣ Render Radar Chart & Comparison Table
# ------------------------------------------------------------
@dash.callback(
    [
        Output("radar-submissions-count", "children"),
        Output("radar-evaluations-count", "children"),
        Output("radar-chart", "figure"),
        Output("comparison-table-section", "children"),
        Output("comparison-data-store", "data"),
    ],
    [
        Input("radar-cache", "data"),
        Input("radar-submission-select", "value"),
        Input("radar-score-select", "value"),
        Input("radar-avg-score-select", "value"),
        Input("radar-date-range", "start_date"),
        Input("radar-date-range", "end_date"),
    ],
    memoize=True,  # Cache results for same inputs to reduce overhead
)
def render_radar_and_table(
    data, submissions, selected_scores, avg_scores, start_date, end_date
):
    if not data:
        return (
            "Submissions: 0",
            "Evaluations: 0",
            go.Figure(),
            html.P("No data available."),
            None,
        )

    df_eval, df_sub = make_dataframes(data)
    if df_eval.empty:
        return (
            "Submissions: 0",
            "Evaluations: 0",
            go.Figure(),
            html.P("No evaluation data."),
            None,
        )

    # ---- Apply filters ----
    if start_date and end_date and "evaluated_at" in df_eval.columns:
        mask = (
            pd.to_datetime(df_eval["evaluated_at"]) >= pd.to_datetime(start_date)
        ) & (pd.to_datetime(df_eval["evaluated_at"]) <= pd.to_datetime(end_date))
        df_eval = df_eval[mask]

    if submissions:
        df_eval["sub_id"] = df_eval["sub_id"].astype(str)
        df_eval = df_eval[df_eval["sub_id"].isin([str(s) for s in submissions])]

    # ---- Compute averages ----
    if df_eval.empty:
        return (
            f"Submissions: {len(df_sub)}",
            "Evaluations: 0",
            go.Figure(),
            html.P("No evaluation data after filters."),
            None,
        )

    # Get base scores per submission
    base_df = df_eval.groupby("sub_id")[SCORE_FIELDS].mean().reset_index()

    # Add avg_ prefixed columns for radar chart compatibility
    avg_df = base_df.copy()
    for score in SCORE_FIELDS:
        avg_df[f"avg_{score}"] = avg_df[score]

    merged_df = avg_df

    # Determine which metrics to show on radar chart (for visualization)
    selected_metrics = []
    if selected_scores:
        selected_metrics.extend([s for s in selected_scores if s in SCORE_FIELDS])
    if avg_scores:
        selected_metrics.extend([a for a in avg_scores if a.startswith("avg_")])

    if not selected_metrics:
        return (
            f"Submissions: {len(df_sub)}",
            f"Evaluations: {len(df_eval)}",
            go.Figure(),
            html.P("No selected metrics found."),
            None,
        )

    # ---- Radar Chart ----
    fig = make_radar_chart(
        merged_df,
        index_col="sub_id",
        selected_rows=submissions,
        selected_metrics=selected_metrics,
    )

    # ---- Comparison Table ----
    # Filter to selected submissions only
    if submissions:
        comparison_df = base_df[
            base_df["sub_id"].isin([str(s) for s in submissions])
        ].copy()
    else:
        comparison_df = base_df.copy()

    if comparison_df.empty:
        return (
            f"Submissions: {len(df_sub)}",
            f"Evaluations: {len(df_eval)}",
            fig,
            html.P("No comparison data available."),
            None,
        )

    # Calculate average of the three scores
    comparison_df["average"] = comparison_df[SCORE_FIELDS].mean(axis=1)

    # Reorder columns to show: sub_id, knowledge, enthusiasm, humor, average
    comparison_df = comparison_df[["sub_id"] + SCORE_FIELDS + ["average"]]
    comparison_df = comparison_df.round(2)

    # Store data for download
    comparison_data = comparison_df.to_dict("records")

    # Use our reusable helper for clean styling
    comparison_table = make_table(comparison_df)

    # ---- Insights ----
    insights = []
    if len(comparison_df) >= 2:
        # Find highest scores by parameter
        comp_indexed = comparison_df.set_index("sub_id")
        max_scores = comp_indexed.idxmax()

        # Get top submissions by average score
        top_submissions = comp_indexed.sort_values("average", ascending=False)

        insights = html.Div(
            [
                html.Hr(),
                html.H4("📊 Comparison Insights", className="mt-3 mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H5("🏁 Highest Scores by Parameter"),
                                html.Ul(
                                    [
                                        html.Li(
                                            f"{param.capitalize()}: {best_sub} "
                                            f"({comp_indexed.loc[best_sub, param]:.2f})"
                                        )
                                        for param, best_sub in max_scores.items()
                                    ]
                                ),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.H5("🏆 Top Submissions by Average Score"),
                                html.Ul(
                                    [
                                        html.Li(f"{sub}: {row['average']:.2f} avg")
                                        for sub, row in top_submissions.head(
                                            10
                                        ).iterrows()
                                    ]
                                ),
                            ],
                            width=6,
                        ),
                    ]
                ),
            ]
        )

    comparison_html = html.Div(
        [
            html.P(
                "Scores: Knowledge, Enthusiasm, Humor, and Overall Average",
                className="text-muted mb-2",
            ),
            dbc.Button(
                "📥 Download Comparison Data",
                id="download-comparison-btn",
                color="primary",
                className="mb-3",
                size="sm",
            ),
            comparison_table,
            insights,
        ]
    )

    return (
        f"Submissions: {len(df_sub)}",
        f"Evaluations: {len(df_eval)}",
        fig,
        comparison_html,
        comparison_data,
    )


# ------------------------------------------------------------
# 4️⃣ Download Callback
# ------------------------------------------------------------
@dash.callback(
    Output("download-comparison-csv", "data"),
    Input("download-comparison-btn", "n_clicks"),
    State("comparison-data-store", "data"),
    prevent_initial_call=True,
)
def download_comparison(n_clicks, data):
    if not data or not n_clicks:
        return dash.no_update

    # Convert data back to DataFrame
    df = pd.DataFrame(data)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"f1_fan_comparison_{timestamp}.csv"

    # Return the download
    return dcc.send_data_frame(df.to_csv, filename, index=False)
