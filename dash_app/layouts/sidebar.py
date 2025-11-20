from dash import dcc, html

nav_links = [
    {"name": "📊 Raw Data", "path": "/raw-data"},
    {"name": "📈 Score Distribution", "path": "/score-distribution"},
    {"name": "⚙️ System Performance", "path": "/system-performance"},
    {"name": "🎯 Radar Comparison", "path": "/radar-comparison"},
]

sidebar = html.Div(
    [
        html.H4("🏎️ F1 Fan Evaluator", className="sidebar-title"),
        html.Hr(className="sidebar-separator"),
        html.Nav(
            [
                html.Ul(
                    [
                        html.Li(
                            dcc.Link(
                                link["name"],
                                href=link["path"],
                                className="nav-link",
                            ),
                            className="nav-item",
                        )
                        for link in nav_links
                    ],
                    className="nav-list",
                )
            ]
        ),
        html.Hr(className="sidebar-separator"),
        html.Button(
            "🔄 Refresh Data",
            id="refresh-button",
            className="refresh-button",
        ),
    ],
    className="sidebar",
)
