# dash_app/utils/ui_helpers.py
from __future__ import annotations

import pandas as pd
from dash import dash_table, html

MAX_ROWS = 50

DEFAULT_TABLE_STYLE = {
    "page_size": MAX_ROWS,
    "virtualization": True,
    "fixed_rows": {"headers": True},
    "sort_action": "native",
    "filter_action": "native",
    "style_table": {
        "overflowX": "auto",  # allow horizontal scrolling
        "overflowY": "auto",
        "maxHeight": "60vh",
        "border": "1px solid #e5e7eb",
        "minWidth": "100%",
    },
    "style_cell": {
        "textAlign": "left",
        "fontSize": 12,
        "padding": "8px",
        "color": "#1f2937",
        "backgroundColor": "#ffffff",
        "border": "1px solid #e5e7eb",
        "whiteSpace": "nowrap",  # Prevent text wrapping - single line only
        "height": "36px",  # Fixed row height (1 unit)
        "minWidth": "120px",
        "width": "auto",
        "maxWidth": "700px",  # limit width to prevent overscroll
        "overflow": "hidden",
        "textOverflow": "ellipsis",
        "lineHeight": "1.5em",
    },
    "style_header": {
        "fontWeight": 700,
        "backgroundColor": "#f3f4f6",
        "color": "#111827",
        "border": "1px solid #e5e7eb",
    },
    "style_data_conditional": [
        {"if": {"row_index": "odd"}, "backgroundColor": "#fbfdff"},
        {
            "if": {"state": "selected"},
            "backgroundColor": "#eef2ff",
            "border": "1px solid #c7d2fe",
        },
    ],
}


def make_table(df: pd.DataFrame, page_size: int | None = None):
    """Standardized Dash DataTable with scroll + resizable columns."""
    if df is None or df.empty:
        return html.Div("No data available.", className="text-muted")

    props = DEFAULT_TABLE_STYLE.copy()
    if page_size is not None:
        props["page_size"] = page_size

    # Build tooltips: full text for each cell (displayed on hover or double-click)
    tooltip_data = [
        {col: {"value": str(val), "type": "markdown"} for col, val in row.items()}
        for row in df.to_dict("records")
    ]

    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[
            {
                "name": c,
                "id": c,
                "deletable": False,
                "hideable": True,
                "editable": False,
            }
            for c in df.columns
        ],
        # allows column resizing
        tooltip_data=tooltip_data,
        tooltip_duration=None,
        editable=True,
        **props,
    )
