from __future__ import annotations

from typing import Iterable, List, Tuple

import dash_bootstrap_components as dbc
from dash import dcc, html


# --------- Reusable UI atoms ---------
def header_bar(title: str, refresh_id: str) -> html.Div:
    return html.Div(
        [
            html.H2(title, className="page-title text-primary"),
            html.Div(
                [
                    dbc.Button(
                        "🔄 Refresh Data",
                        id=refresh_id,
                        color="primary",
                        className="btn-brand",
                    ),
                ],
                className="header-actions",
            ),
        ],
        className="page-header",
    )


def kpi_chips(counters: Iterable[Tuple[str, str]]) -> html.Div:
    """
    counters: list of tuples: (component_id, label)
    Renders badges with dynamic children controlled by callbacks elsewhere.
    """
    chips = []
    for comp_id, label in counters:
        chips.append(
            html.Div(
                [
                    html.Span(f"{label}:", className="kpi-label"),
                    html.Span(id=comp_id, className="kpi-value"),
                ],
                className="kpi-chip",
            )
        )
    return html.Div(chips, className="kpi-row")


def controls_card(controls_children: List) -> html.Div:
    if not controls_children:
        return html.Div()
    return html.Div(controls_children, className="controls-card")


def section_card(title: str, body_id: str) -> html.Div:
    return html.Div(
        [html.H4(title), html.Div(id=body_id, className="section-body")],
        className="section-card",
    )


def data_store(cache_id: str) -> dcc.Store:
    return dcc.Store(id=cache_id, storage_type="memory")


# --------- Page assembly ---------
def compose_page(
    *,
    title: str,
    refresh_id: str,
    cache_id: str,
    counters: Iterable[Tuple[str, str]] = (),
    controls: List = None,
    sections: Iterable[Tuple[str, str]] = (),
) -> html.Div:
    """
    Produces a consistent, polished page section to drop into the main container.
    Keeps all IDs and section IDs as passed (so callbacks don't break).
    """
    controls = controls or []
    return html.Div(
        [
            header_bar(title, refresh_id),
            data_store(cache_id),
            kpi_chips(counters),
            controls_card(controls),
            html.Hr(className="hr-muted"),
            *[section_card(title, sec_id) for (title, sec_id) in sections],
        ],
        className="main-pane",
    )
