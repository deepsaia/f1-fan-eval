"""
Dash Application - Interactive dashboards for F1 fan evaluation results.

This is the main entry point for the Dash web application that provides:
- Raw data viewing (submissions and evaluations)
- Score distribution analysis (histograms, box plots)
- Radar chart comparisons (multi-dimensional comparison)
- System performance metrics (token usage, processing times)

The app uses Dash's multi-page feature, with pages defined in dash_app/pages/

To run:
    python dash_app/app.py

Then open: http://127.0.0.1:8050
"""

import dash
import dash_bootstrap_components as dbc
from dash import Dash, dcc

from dash_app.layouts.sidebar import sidebar

# Create Dash application
app = Dash(
    __name__,
    use_pages=True,  # Enable multi-page support (pages in dash_app/pages/)
    external_stylesheets=[
        dbc.themes.FLATLY,  # Modern, clean Bootstrap theme
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",  # Modern font
    ],
    suppress_callback_exceptions=True,  # Needed for multi-page apps with dynamic callbacks
)

# Define application layout
# Uses a 2-column layout: sidebar (2 cols) + main content (10 cols)
app.layout = dbc.Container(
    [
        dbc.Row(
            [
                # Left sidebar with navigation
                dbc.Col(sidebar, width=2),

                # Main content area with loading spinner
                # dash.page_container auto-renders the selected page
                dbc.Col(
                    dcc.Loading(children=[dash.page_container]),
                    width=10,
                    className="main-col",
                ),
            ],
            className="g-0",  # Remove gutter spacing
        )
    ],
    fluid=True,  # Full-width container
)

# Run the app when executed directly
if __name__ == "__main__":
    app.run(
        debug=True,          # Enable hot-reload and debug mode
        host="127.0.0.1",    # Local host only
        port=8050            # Default Dash port
    )
