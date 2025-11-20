from __future__ import annotations

from typing import List, Tuple

from dash import dcc, html

from dash_app.layouts.base_layout import (
    controls_card,
    data_store,
    header_bar,
    kpi_chips,
    section_card,
)


def make_dashboard_layout(
    title: str,
    refresh_id: str,
    cache_id: str,
    counters: list[Tuple[str, str]] | None = None,
    controls: list | None = None,
    sections: list[Tuple[str, str]] | None = None,
    graphs: list[str] | None = None,
    fluid: bool = True,
) -> html.Div:
    """
    Generic layout builder for dashboards with consistent structure.

    Parameters
    ----------
    title : str
        Page title (with emoji optional).
    refresh_id : str
        ID for the refresh button.
    cache_id : str
        ID for the dcc.Store cache component.
    counters : list[(str, str)]
        Pairs of (id, label) for numeric badges.
    controls : list
        List of dbc.Row or dbc.Col elements representing filters/controls.
    sections : list[(str, str)]
        Pairs of (section_title, div_id) for data tables or subsections.
    graphs : list[str]
        List of Graph IDs to be wrapped with dcc.Loading.
    """
    counters = counters or []
    controls = controls or []
    sections = sections or []
    graphs = graphs or []

    children: List = [
        header_bar(title, refresh_id),
        data_store(cache_id),
    ]

    # Counter badges row
    if counters:
        children.append(kpi_chips(counters))

    if controls:
        children.append(controls_card(controls))

    # light divider between controls and content
    children.append(html.Hr(className="hr-muted"))

    # section cards (tables/blocks)
    for sec_title, sec_id in sections:
        children.append(section_card(sec_title, sec_id))

    # graph blocks (each as its own section card so it looks consistent)
    for graph_id in graphs:
        children.append(
            html.Div(
                [
                    dcc.Loading(dcc.Graph(id=graph_id)),
                ],
                className="section-card",
            )
        )

    # wrap everything in a main pane for global padding/background
    return html.Div(children, className="main-pane")
