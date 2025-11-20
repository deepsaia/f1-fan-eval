import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COLORS = px.colors.qualitative.Set1
ALT_COLORS = px.colors.qualitative.G10


def make_histograms(df, columns, nbinsx: int = 20, title: str | None = None):
    """
    Generate subplot histograms for selected columns with unified scale and bins.

    Parameters
    ----------
    df : pd.DataFrame
        The data source.
    columns : list[str]
        List of column names to plot.
    nbinsx : int, optional
        Number of bins for histograms.
    title : str, optional
        Custom plot title.
    """
    if not columns or df.empty:
        return go.Figure()

    # Ensure numeric columns only
    cols = [c for c in columns if c in df.columns and df[c].dtype.kind in "if"]
    if not cols:
        return go.Figure()

    # Calculate common min/max across all columns for unified bins
    all_values = pd.concat([df[col].dropna() for col in cols])
    if all_values.empty:
        return go.Figure()

    data_min = all_values.min()
    data_max = all_values.max()

    # Calculate bin edges for consistent binning
    bin_edges = pd.cut(pd.Series([data_min, data_max]), bins=nbinsx, retbins=True)[1]

    fig = make_subplots(rows=1, cols=len(cols), subplot_titles=cols)

    # Track max count for unified y-axis
    max_count = 0

    # First pass: create histograms and find max count
    for i, col in enumerate(cols, start=1):
        # Use the same bins for all histograms
        hist_data, _ = pd.cut(
            df[col].dropna(), bins=bin_edges, include_lowest=True, retbins=True
        )
        counts = hist_data.value_counts().values
        if len(counts) > 0:
            max_count = max(max_count, counts.max())

        fig.add_trace(
            go.Histogram(
                x=df[col],
                xbins=dict(
                    start=data_min, end=data_max, size=(data_max - data_min) / nbinsx
                ),
                marker_color=COLORS[i % len(COLORS)],
                name=col,
            ),
            row=1,
            col=i,
        )

    # Update all y-axes to have the same range
    for i in range(1, len(cols) + 1):
        fig.update_yaxes(range=[0, max_count * 1.1], row=1, col=i)

    fig.update_layout(
        title=title or "Distribution by Column",
        height=400,
        showlegend=False,
        bargap=0.1,
    )
    return fig


def make_boxplots(df, columns, title: str | None = None):
    """
    Generate box plots for selected columns.

    Parameters
    ----------
    df : pd.DataFrame
        The data source.
    columns : list[str]
        List of column names to plot.
    title : str, optional
        Custom plot title.
    """
    if not columns or df.empty:
        return go.Figure()

    cols = [c for c in columns if c in df.columns and df[c].dtype.kind in "if"]
    if not cols:
        return go.Figure()

    fig = go.Figure()
    for i, col in enumerate(cols):
        fig.add_trace(
            go.Box(
                y=df[col],
                name=col,
                boxpoints="outliers",
                marker_color=COLORS[i % len(COLORS)],
            )
        )

    fig.update_layout(
        title=title or "Box Plot Comparison",
        yaxis_title="Value",
        height=500,
    )
    return fig


def make_radar_chart(
    df,
    index_col: str,
    selected_rows: list[str],
    selected_metrics: list[str],
    title: str = "Radar Chart Comparison",
):
    """
    Create a radar (polar) chart comparing multiple rows (e.g. submissions) across selected metrics.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with metrics to plot.
    index_col : str
        Column name to use as the row identifier (e.g. 'sub_id').
    selected_rows : list[str]
        Rows to include (values from index_col).
    selected_metrics : list[str]
        Columns (numeric) to plot.
    title : str
        Title of the chart.
    """
    if df.empty or not selected_metrics or not selected_rows:
        return go.Figure()

    # Ensure required data is present
    missing = [c for c in selected_metrics if c not in df.columns]
    if missing:
        selected_metrics = [c for c in selected_metrics if c in df.columns]

    if len(selected_metrics) < 3:
        fig = go.Figure()
        fig.update_layout(
            title="Please select at least 3 parameters for a meaningful radar chart."
        )
        return fig

    fig = go.Figure()
    label_map = {
        param: param.replace("avg_", "Average ").replace("_", " ").title()
        for param in selected_metrics
    }
    theta = list(label_map.values())
    colors = COLORS
    global_max = 0

    for i, sub_id in enumerate(selected_rows):
        if sub_id not in df[index_col].values:
            continue
        row = df[df[index_col] == sub_id].iloc[0]
        values = [
            row.get(param, 0) if pd.notna(row.get(param)) else 0
            for param in selected_metrics
        ]
        values.append(values[0])
        theta_closed = theta + [theta[0]]
        global_max = max(global_max, max(values, default=0))
        fig.add_trace(
            go.Scatterpolar(
                r=values,
                theta=theta_closed,
                fill="toself",
                name=sub_id,
                line_color=colors[i % len(colors)],
                fillcolor=colors[i % len(colors)],
                opacity=0.3,
            )
        )

    radial_max = min(100, int((global_max + 9) // 10 * 10))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, radial_max])),
        title=title,
        showlegend=True,
        height=600,
    )
    return fig


def make_time_series(
    df,
    metrics,
    avg_metrics=None,
    time_col="evaluated_at",
    title: str = "📈 Trends Over Time",
):
    """
    Generate a multi-series time plot for selected metrics.

    Parameters
    ----------
    df : pd.DataFrame
        The data containing time column and metric columns.
    metrics : list[str]
        Column names to plot (raw metrics).
    avg_metrics : list[str], optional
        Average/aggregate metric columns, will be plotted with dashed lines.
    time_col : str, default "evaluated_at"
        Name of the datetime column.

    Returns
    -------
    go.Figure
        A Plotly figure with line+marker traces.
    """
    if df.empty or time_col not in df.columns:
        return go.Figure()

    df = df.copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])

    fig = go.Figure()

    # --- Plot raw metrics ---
    for i, metric in enumerate(metrics or []):
        if metric in df.columns:
            df_metric = df.groupby(time_col)[metric].mean().reset_index()
            if not df_metric.empty:
                fig.add_trace(
                    go.Scatter(
                        x=df_metric[time_col],
                        y=df_metric[metric],
                        mode="lines+markers",
                        name=metric.replace("_", " ").title(),
                        line=dict(color=COLORS[i % len(COLORS)]),
                    )
                )

    # --- Plot average metrics (dashed lines) ---
    for j, metric in enumerate(avg_metrics or []):
        base = metric.replace("avg_", "")
        if base in df.columns:
            df_metric = df.groupby(time_col)[base].mean().reset_index()
            if not df_metric.empty:
                fig.add_trace(
                    go.Scatter(
                        x=df_metric[time_col],
                        y=df_metric[base],
                        mode="lines",
                        name=metric.replace("_", " ").title(),
                        line=dict(
                            color=ALT_COLORS[j % len(ALT_COLORS)],
                            dash="dot",
                        ),
                    )
                )

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Metric Value",
        height=500,
        hovermode="x unified",
        legend_title="Metrics",
    )

    return fig
