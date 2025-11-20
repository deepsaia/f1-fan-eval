# dash_app/pages/raw_data.py
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, html

from dash_app.utils.data_helpers import get_data_dict, make_dataframes
from dash_app.utils.layout_helper import make_dashboard_layout
from dash_app.utils.ui_helpers import make_table

dash.register_page(__name__, path="/raw-data", name="📊 Raw Data")

MAX_ROWS = 50

layout = make_dashboard_layout(
    title="📊 Raw Data Tables",
    refresh_id="refresh-data-btn",
    cache_id="data-cache",
    counters=[
        ("raw-submission-count", "Submissions"),
        ("raw-evaluation-count", "Evaluations"),
    ],
    controls=[
        dbc.Row(
            [
                dbc.Col(
                    dbc.Checkbox(id="granular-toggle", label="Granular", value=False),
                    width=2,
                ),
                dbc.Col(
                    dbc.Input(
                        id="search-sub",
                        placeholder="🔍 Search submissions...",
                        type="text",
                    ),
                    width=5,
                ),
                dbc.Col(
                    dbc.Input(
                        id="search-eval",
                        placeholder="🔍 Search evaluations...",
                        type="text",
                    ),
                    width=5,
                ),
            ],
            className="mb-3 g-2",
        )
    ],
    sections=[
        ("📝 Submissions Table", "submissions-table"),
        ("📈 Evaluations Table", "evaluations-table"),
        ("🧮 Nulls in Submissions Table", "nulls-table"),
        ("📂 Submissions with Default Files", "default-files-table"),
    ],
)


# ---- 1️⃣ Load and cache data ----
@dash.callback(
    Output("data-cache", "data"),
    Input("refresh-data-btn", "n_clicks"),
    prevent_initial_call=False,
)
def load_data(n_clicks):
    return get_data_dict()


# ---- 2️⃣ Filter + render tables ----
@dash.callback(
    [
        Output("submissions-table", "children"),
        Output("evaluations-table", "children"),
        Output("raw-submission-count", "children"),
        Output("raw-evaluation-count", "children"),
        Output("nulls-table", "children"),
        Output("default-files-table", "children"),
    ],
    [
        Input("data-cache", "data"),
        Input("granular-toggle", "value"),
        Input("search-sub", "value"),
        Input("search-eval", "value"),
    ],
    memoize=True,  # cache results for same inputs
)
def render_tables(data, granular, search_sub, search_eval):
    if not data:
        return ["No data."] * 6

    df_eval, df_sub = make_dataframes(data)

    if not granular and "input_type" in df_eval.columns:
        df_eval = df_eval[df_eval["input_type"] == "text"]

    eval_count, sub_count = len(df_eval), len(df_sub)

    if search_sub:
        df_sub = df_sub[
            df_sub["sub_id"].astype(str).str.contains(search_sub, case=False, na=False)
        ]
    if search_eval:
        df_eval = df_eval[
            df_eval["sub_id"]
            .astype(str)
            .str.contains(search_eval, case=False, na=False)
        ]

    submissions_table = make_table(df_sub)
    evaluations_table = make_table(df_eval)

    # Nulls and defaults same logic as before but without head()
    # ...
    return (
        submissions_table,
        evaluations_table,
        f"Submissions: {sub_count}",
        f"Evaluations: {eval_count}",
        html.P("Nulls analysis here"),
        html.P("Default files table here"),
    )
