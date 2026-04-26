"""Overview page — KPI cards, timeline chart, model pie, workspace & session tables."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dash_table, dcc, html, no_update

from copilot_usage.dashboard import queries
from copilot_usage.dashboard.app import empty_fig, fmt_number, kpi_card, short_path

dash.register_page(__name__, path="/", name="Overview", order=0)


# ---------------------------------------------------------------------------
# Date filter helpers (shared pattern for all detail modals)
# ---------------------------------------------------------------------------

_DATE_PRESET_OPTIONS = [
    {"label": "Today",      "value": "today"},
    {"label": "This Week",  "value": "this_week"},
    {"label": "Last Week",  "value": "last_week"},
    {"label": "This Month", "value": "this_month"},
    {"label": "Last Month", "value": "last_month"},
    {"label": "All Time",   "value": "all_time"},
    {"label": "Custom",     "value": "custom"},
]


def _resolve_date_range(
    preset: str,
    custom_start: str | None,
    custom_end: str | None,
) -> tuple[str | None, str | None, str]:
    """Return (start_iso, end_iso, label_text) for a given preset."""
    today = date.today()

    if preset == "today":
        s = e = today.isoformat()
        label = f"Today  ·  {today.strftime('%b %d, %Y')}"

    elif preset == "this_week":
        monday = today - timedelta(days=today.weekday())
        s, e = monday.isoformat(), today.isoformat()
        label = f"This Week  ·  {monday.strftime('%b %d')} – {today.strftime('%b %d, %Y')}"

    elif preset == "last_week":
        last_mon = today - timedelta(days=today.weekday() + 7)
        last_sun = last_mon + timedelta(days=6)
        s, e = last_mon.isoformat(), last_sun.isoformat()
        label = f"Last Week  ·  {last_mon.strftime('%b %d')} – {last_sun.strftime('%b %d, %Y')}"

    elif preset == "this_month":
        first = today.replace(day=1)
        s, e = first.isoformat(), today.isoformat()
        label = f"This Month  ·  {first.strftime('%b %d')} – {today.strftime('%b %d, %Y')}"

    elif preset == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        s, e = first_prev.isoformat(), last_prev.isoformat()
        label = f"Last Month  ·  {first_prev.strftime('%b %d')} – {last_prev.strftime('%b %d, %Y')}"

    elif preset == "custom":
        s, e = custom_start, custom_end
        if s and e:
            sd = datetime.fromisoformat(s).strftime("%b %d, %Y")
            ed = datetime.fromisoformat(e).strftime("%b %d, %Y")
            label = f"Custom  ·  {sd} – {ed}"
        elif s:
            label = f"Custom  ·  From {datetime.fromisoformat(s).strftime('%b %d, %Y')}"
        else:
            label = "Custom  ·  Select a date range"

    else:  # all_time
        s = e = None
        label = "All Time"

    return s, e, label


# ---------------------------------------------------------------------------
# Premium modal helpers
# ---------------------------------------------------------------------------

_PREM_COLUMNS = [
    {"name": "Date",         "id": "date",              "type": "text"},
    {"name": "Model",        "id": "model_id",          "type": "text"},
    {"name": "Workspace",    "id": "workspace_path",    "type": "text"},
    {"name": "Session",      "id": "session_short",     "type": "text"},
    {"name": "Tool Calls",   "id": "tool_call_rounds",  "type": "numeric"},
    {"name": "Premium Est.", "id": "premium_estimate",  "type": "numeric"},
    {"name": "Estimated",    "id": "tokens_estimated",  "type": "text"},
]


# ---------------------------------------------------------------------------
# Requests modal helpers
# ---------------------------------------------------------------------------

_REQ_COLUMNS = [
    {"name": "Date",           "id": "date",            "type": "text"},
    {"name": "Session",        "id": "session_short",   "type": "text"},
    {"name": "#",              "id": "request_index",   "type": "numeric"},
    {"name": "Request ID",     "id": "request_id",      "type": "text"},
    {"name": "Model",          "id": "model_id",        "type": "text"},
    {"name": "Prompt Tokens",  "id": "prompt_tokens",   "type": "numeric"},
    {"name": "Output Tokens",  "id": "output_tokens",   "type": "numeric"},
    {"name": "Tool Calls",     "id": "tool_call_rounds","type": "numeric"},
    {"name": "Premium Est.",   "id": "premium_estimate","type": "numeric"},
    {"name": "Estimated",      "id": "tokens_estimated","type": "text"},
    {"name": "Source",         "id": "data_source",     "type": "text"},
    {"name": "Workspace",      "id": "workspace_path",  "type": "text"},
]

_TABLE_STYLE_HEADER = {
    "backgroundColor": "#161b22",
    "color": "#8b949e",
    "fontWeight": "600",
    "fontSize": "0.78rem",
    "textTransform": "uppercase",
    "letterSpacing": "0.4px",
    "borderBottom": "1px solid #30363d",
    "borderTop": "none",
    "padding": "10px 12px",
    "whiteSpace": "nowrap",
}
_TABLE_STYLE_CELL = {
    "backgroundColor": "#0d1117",
    "color": "#c9d1d9",
    "fontSize": "0.85rem",
    "border": "none",
    "borderBottom": "1px solid #21262d",
    "padding": "8px 12px",
    "textAlign": "left",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "maxWidth": "200px",
}
_TABLE_STYLE_DATA_CONDITIONAL = [
    {"if": {"row_index": "odd"}, "backgroundColor": "rgba(255,255,255,.025)"},
    {"if": {"state": "active"},  "backgroundColor": "rgba(88,166,255,.08)", "border": "1px solid #58a6ff"},
    {
        "if": {"filter_query": '{data_source} = "legacy_json"'},
        "color": "#d29922",
    },
    {
        "if": {"filter_query": '{tokens_estimated} = "Yes"'},
        "color": "#d29922",
    },
]


def _build_req_table(rows: list[dict]) -> dash_table.DataTable | html.P:
    if not rows:
        return html.P("No requests in this date range.", className="text-muted p-3 mb-0")
    return dash_table.DataTable(
        id="ov-req-datatable",
        data=rows,
        columns=_REQ_COLUMNS,
        sort_action="native",
        sort_mode="single",
        page_action="native",
        page_size=50,
        style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "55vh"},
        style_header=_TABLE_STYLE_HEADER,
        style_cell=_TABLE_STYLE_CELL,
        style_data_conditional=_TABLE_STYLE_DATA_CONDITIONAL,
        style_as_list_view=True,
    )


def _build_prem_table(rows: list[dict]) -> dash_table.DataTable | html.P:
    if not rows:
        return html.P("No premium requests in this date range.", className="text-muted p-3 mb-0")
    return dash_table.DataTable(
        id="ov-prem-datatable",
        data=rows,
        columns=_PREM_COLUMNS,
        sort_action="native",
        sort_mode="single",
        page_action="native",
        page_size=50,
        style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "55vh"},
        style_header=_TABLE_STYLE_HEADER,
        style_cell=_TABLE_STYLE_CELL,
        style_data_conditional=_TABLE_STYLE_DATA_CONDITIONAL,
        style_as_list_view=True,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    # KPI row
    dbc.Row(id="ov-kpi-row", className="g-3 mb-4"),

    # Charts
    dbc.Row([
        dbc.Col(
            html.Div([
                html.Div("Daily Token Usage", className="card-header"),
                dcc.Graph(id="ov-timeline", config={"displayModeBar": False}),
            ], className="section-card"),
            lg=8,
        ),
        dbc.Col(
            html.Div([
                html.Div("Model Distribution", className="card-header"),
                dcc.Graph(id="ov-model-pie", config={"displayModeBar": False}),
            ], className="section-card"),
            lg=4,
        ),
    ], className="g-3 mb-4"),

    # Data source breakdown chart
    dbc.Row([
        dbc.Col(
            html.Div([
                html.Div([
                    html.Span("Data Source Breakdown"),
                    html.Span(
                        " JSONL = actual tokens · Legacy JSON = estimated tokens",
                        className="text-muted ms-2",
                        style={"fontSize": "0.75rem", "fontWeight": "400"},
                    ),
                ], className="card-header"),
                dcc.Graph(id="ov-source-chart", config={"displayModeBar": False}),
            ], className="section-card"),
            lg=12,
        ),
    ], className="g-3 mb-4"),

    # Tables
    dbc.Row([
        dbc.Col(
            html.Div([
                html.Div("Workspaces", className="card-header"),
                html.Div(id="ov-workspace-table", className="p-0"),
            ], className="section-card"),
            lg=6,
        ),
        dbc.Col(
            html.Div([
                html.Div("Recent Sessions", className="card-header"),
                html.Div(id="ov-session-table", className="p-0"),
            ], className="section-card"),
            lg=6,
        ),
    ], className="g-3 mb-4"),

    # ── Premium detail modal ───────────────────────────────────────────────
    dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle([
                    html.I(className="bi bi-gem me-2"),
                    "Premium Requests",
                ]),
                close_button=True,
            ),
            dbc.ModalBody([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.Label("Date Range", className="modal-filter-label"),
                            dcc.Dropdown(
                                id="ov-prem-date-preset",
                                options=_DATE_PRESET_OPTIONS,
                                value="all_time",
                                clearable=False,
                                searchable=False,
                                className="dash-dark-dropdown",
                            ),
                        ], md=3),
                        dbc.Col(
                            html.Div(
                                dcc.DatePickerRange(
                                    id="ov-prem-date-picker",
                                    display_format="YYYY-MM-DD",
                                    start_date_placeholder_text="From",
                                    end_date_placeholder_text="To",
                                    style={"width": "100%"},
                                    className="dash-dark-datepicker",
                                ),
                                id="ov-prem-custom-wrap",
                                style={"display": "none"},
                            ),
                            md=6,
                            className="d-flex align-items-end",
                        ),
                    ], align="end"),
                ], className="modal-filter-bar mb-3"),
                html.Div(id="ov-prem-range-label", className="modal-range-label mb-3"),
                html.Div(id="ov-prem-table"),
            ]),
        ],
        id="ov-prem-modal",
        is_open=False,
        size="xl",
        dialogClassName="modal-75",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    ),

    # ── Requests detail modal ──────────────────────────────────────────────
    dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle([
                    html.I(className="bi bi-list-ul me-2"),
                    "Requests",
                ]),
                close_button=True,
            ),
            dbc.ModalBody([
                # Date filter bar
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.Label("Date Range", className="modal-filter-label"),
                            dcc.Dropdown(
                                id="ov-req-date-preset",
                                options=_DATE_PRESET_OPTIONS,
                                value="all_time",
                                clearable=False,
                                searchable=False,
                                className="dash-dark-dropdown",
                            ),
                        ], md=3),
                        dbc.Col(
                            html.Div(
                                dcc.DatePickerRange(
                                    id="ov-req-date-picker",
                                    display_format="YYYY-MM-DD",
                                    start_date_placeholder_text="From",
                                    end_date_placeholder_text="To",
                                    style={"width": "100%"},
                                    className="dash-dark-datepicker",
                                ),
                                id="ov-req-custom-wrap",
                                style={"display": "none"},
                            ),
                            md=6,
                            className="d-flex align-items-end",
                        ),
                    ], align="end"),
                ], className="modal-filter-bar mb-3"),

                # Active range label + row count
                html.Div(id="ov-req-range-label", className="modal-range-label mb-3"),

                # Data table (replaced on filter change)
                html.Div(id="ov-req-table"),
            ]),
        ],
        id="ov-req-modal",
        is_open=False,
        size="xl",
        dialogClassName="modal-75",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    ),

    # Trigger initial load
    dcc.Interval(id="ov-init", interval=300, max_intervals=1),
])


# ---------------------------------------------------------------------------
# Callbacks — KPI cards & charts
# ---------------------------------------------------------------------------

@callback(Output("ov-kpi-row", "children"), Input("ov-init", "n_intervals"))
def _kpis(_):
    kpi = queries.kpi_totals()
    legacy = kpi.get("legacy_events", 0) or 0
    estimated = kpi.get("estimated_events", 0) or 0
    total = kpi["total_requests"]
    new_count = total - legacy

    cards = [
        kpi_card("Requests",      f"{total:,}",                       "📨", card_id="ov-req-card"),
        kpi_card("Prompt Tokens",  fmt_number(kpi["total_prompt"]),    "📝"),
        kpi_card("Output Tokens",  fmt_number(kpi["total_output"]),    "💬"),
        kpi_card("Premium Est.",   f"~{kpi['total_premium']:,.0f}",   "💎", card_id="ov-prem-card"),
        kpi_card("Workspaces",     str(kpi["workspaces"]),             "📂"),
        kpi_card("Sessions",       str(kpi["sessions"]),               "🗂️"),
    ]

    # Data-source breakdown bar (full-width, sits inside same Row)
    source_bar = dbc.Col(
        html.Div([
            html.Div([
                html.Span("📊", style={"fontSize": "1.1rem", "marginRight": "0.5rem"}),
                html.Span("Data Sources", className="kpi-label",
                          style={"textTransform": "uppercase", "letterSpacing": "0.5px"}),
            ], className="d-inline-flex align-items-center me-4"),
            html.Div([
                html.Span(f"{new_count:,}", style={"color": "#58a6ff", "fontWeight": "700", "fontSize": "1.1rem"}),
                html.Span(" JSONL", className="text-muted ms-1", style={"fontSize": ".8rem"}),
                html.Span("  ·  ", className="text-muted mx-2"),
                html.Span(f"{legacy:,}", style={"color": "#d29922", "fontWeight": "700", "fontSize": "1.1rem"}),
                html.Span(" Legacy", className="text-muted ms-1", style={"fontSize": ".8rem"}),
            ], className="d-inline-flex align-items-baseline me-4"),
            html.Div(
                f"({estimated:,} events with estimated tokens)",
                className="text-muted d-inline",
                style={"fontSize": ".78rem"},
            ) if estimated else None,
        ], className="kpi-card d-flex align-items-center justify-content-center flex-wrap px-4 py-2"),
        xs=12,
    )

    return cards + [source_bar]


@callback(Output("ov-timeline", "figure"), Input("ov-init", "n_intervals"))
def _timeline(_):
    rows = queries.daily_timeseries()
    if not rows:
        return empty_fig("No data yet")
    df = pd.DataFrame(rows)
    df["model_short"] = df["model"].str.replace("copilot/", "", regex=False)
    fig = px.bar(
        df, x="date", y="prompt_tokens", color="model_short",
        labels={"prompt_tokens": "Prompt Tokens", "date": "", "model_short": "Model"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=30, l=60, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        bargap=0.15,
        xaxis=dict(gridcolor="rgba(48,54,61,.5)"),
        yaxis=dict(gridcolor="rgba(48,54,61,.5)"),
    )
    return fig


@callback(Output("ov-source-chart", "figure"), Input("ov-init", "n_intervals"))
def _source_chart(_):
    rows = queries.daily_by_source()
    if not rows:
        return empty_fig("No data yet")
    df = pd.DataFrame(rows)
    label_map = {"jsonl": "JSONL (actual)", "legacy_json": "Legacy JSON (estimated)"}
    df["source_label"] = df["source"].map(label_map).fillna(df["source"])
    color_map = {"JSONL (actual)": "#58a6ff", "Legacy JSON (estimated)": "#d29922"}
    fig = go.Figure()
    for src_label, grp in df.groupby("source_label"):
        fig.add_trace(go.Bar(
            x=grp["date"], y=grp["prompt_tokens"],
            name=src_label,
            marker_color=color_map.get(src_label, "#888"),
        ))
    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=30, l=60, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        bargap=0.15,
        xaxis=dict(gridcolor="rgba(48,54,61,.5)", title=""),
        yaxis=dict(gridcolor="rgba(48,54,61,.5)", title="Prompt Tokens"),
    )
    return fig


@callback(Output("ov-model-pie", "figure"), Input("ov-init", "n_intervals"))
def _model_pie(_):
    rows = queries.model_mix()
    if not rows:
        return empty_fig("No data yet")
    df = pd.DataFrame(rows)
    df["model_short"] = df["model"].str.replace("copilot/", "", regex=False)
    fig = px.pie(
        df, values="total_tokens", names="model_short",
        color_discrete_sequence=px.colors.qualitative.Set2,
        hole=0.45,
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(font=dict(size=11)),
    )
    fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=11)
    return fig


@callback(Output("ov-workspace-table", "children"), Input("ov-init", "n_intervals"))
def _ws_table(_):
    rows = queries.workspace_table()
    if not rows:
        return html.P("No data yet", className="text-muted p-3")
    header = html.Thead(html.Tr([
        html.Th("Workspace"), html.Th("Requests"), html.Th("Prompt"),
        html.Th("Output"), html.Th("Premium"), html.Th("Top Model"),
    ]))
    body = html.Tbody([
        html.Tr([
            html.Td(short_path(r["workspace_path"]), title=r["workspace_path"]),
            html.Td(f"{r['requests']:,}"),
            html.Td(fmt_number(r["prompt_tokens"])),
            html.Td(fmt_number(r["output_tokens"])),
            html.Td(f"~{r['premium']:.0f}"),
            html.Td((r["top_model"] or "").replace("copilot/", "")),
        ]) for r in rows
    ])
    return dbc.Table([header, body], striped=True, hover=True, size="sm",
                     color="dark", className="mb-0")


@callback(Output("ov-session-table", "children"), Input("ov-init", "n_intervals"))
def _sess_table(_):
    rows = queries.session_list(limit=50)
    if not rows:
        return html.P("No data yet", className="text-muted p-3")
    header = html.Thead(html.Tr([
        html.Th("Session"), html.Th("Workspace"), html.Th("Model"),
        html.Th("Reqs"), html.Th("Prompt"), html.Th("Output"), html.Th("Prem."),
    ]))
    body = html.Tbody([
        html.Tr([
            html.Td(r["session_id"][:12] + "…", title=r["session_id"]),
            html.Td(short_path(r["workspace_path"]), title=r["workspace_path"]),
            html.Td((r["model"] or "").replace("copilot/", "")),
            html.Td(str(r["requests"])),
            html.Td(fmt_number(r["prompt_tokens"])),
            html.Td(fmt_number(r["output_tokens"])),
            html.Td(f"~{r['premium']:.0f}"),
        ]) for r in rows
    ])
    return dbc.Table([header, body], striped=True, hover=True, size="sm",
                     color="dark", className="mb-0")


# ---------------------------------------------------------------------------
# Callbacks — Requests modal
# ---------------------------------------------------------------------------

@callback(
    Output("ov-req-modal", "is_open"),
    Input("ov-req-card", "n_clicks"),
    prevent_initial_call=True,
)
def _open_req_modal(n_clicks):
    return bool(n_clicks and n_clicks > 0)


@callback(
    Output("ov-req-custom-wrap", "style"),
    Output("ov-req-range-label", "children"),
    Output("ov-req-table", "children"),
    Input("ov-req-modal", "is_open"),
    Input("ov-req-date-preset", "value"),
    Input("ov-req-date-picker", "start_date"),
    Input("ov-req-date-picker", "end_date"),
    prevent_initial_call=True,
)
def _update_req_modal(is_open, preset, custom_start, custom_end):
    if not is_open:
        return no_update, no_update, no_update

    start, end, label_text = _resolve_date_range(preset, custom_start, custom_end)
    custom_style = {"display": "block"} if preset == "custom" else {"display": "none"}

    rows = queries.requests_table(start_date=start, end_date=end)

    range_label = html.Div([
        html.Span(label_text, className="modal-range-text"),
        html.Span(
            f"  ·  {len(rows):,} request{'s' if len(rows) != 1 else ''}",
            className="text-muted",
            style={"fontSize": "0.85rem"},
        ),
    ])

    return custom_style, range_label, _build_req_table(rows)


@callback(
    Output("ov-prem-modal", "is_open"),
    Input("ov-prem-card", "n_clicks"),
    prevent_initial_call=True,
)
def _open_prem_modal(n_clicks):
    return bool(n_clicks and n_clicks > 0)


@callback(
    Output("ov-prem-custom-wrap", "style"),
    Output("ov-prem-range-label", "children"),
    Output("ov-prem-table", "children"),
    Input("ov-prem-modal", "is_open"),
    Input("ov-prem-date-preset", "value"),
    Input("ov-prem-date-picker", "start_date"),
    Input("ov-prem-date-picker", "end_date"),
    prevent_initial_call=True,
)
def _update_prem_modal(is_open, preset, custom_start, custom_end):
    if not is_open:
        return no_update, no_update, no_update

    start, end, label_text = _resolve_date_range(preset, custom_start, custom_end)
    custom_style = {"display": "block"} if preset == "custom" else {"display": "none"}

    rows = queries.premium_requests_table(start_date=start, end_date=end)

    range_label = html.Div([
        html.Span(label_text, className="modal-range-text"),
        html.Span(
            f"  ·  {len(rows):,} premium request{'s' if len(rows) != 1 else ''}",
            className="text-muted",
            style={"fontSize": "0.85rem"},
        ),
    ])

    return custom_style, range_label, _build_prem_table(rows)
