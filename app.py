import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objs as go
from flask import Response
import io
from pymongo import MongoClient
from datetime import datetime, timedelta

# MongoDB connection
MONGO_URI = "mongodb+srv://shlok:xa0wqvAwSzrjSox9@developmentcluster.6slxuhw.mongodb.net/"
DATABASE_NAME = "cgf"
COLLECTIONS = [
    "gas-flow-oc",
    "gas-temp",
    "methane-conc",
    "pressure",
    "battery-per",
]

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

# Helper functions to fetch data
def get_device_ids():
    ids = set()
    for coll in COLLECTIONS:
        try:
            pipeline = [{"$group": {"_id": "$device_id"}}]
            result = db[coll].aggregate(pipeline)
            ids.update([doc["_id"] for doc in result])
        except Exception:
            pass
    return sorted(ids)

def fetch_latest_metrics(device_id):
    metrics = {}
    for coll in COLLECTIONS:
        pipeline = [
            {"$match": {"device_id": device_id}},
            {"$sort": {"timestamp": -1}},
            {"$limit": 1}
        ]
        docs = list(db[coll].aggregate(pipeline))
        if docs:
            metrics[coll] = docs[0]
    return metrics

def fetch_gas_production_history(device_id, days):
    since = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"device_id": device_id, "timestamp": {"$gte": since}}},
        {"$sort": {"timestamp": 1}}
    ]
    data = list(db["gas-flow-oc"].aggregate(pipeline))
    df = pd.DataFrame(data)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

def fetch_and_merge_data(device_id):
    dfs = []
    for coll in COLLECTIONS:
        pipeline = [
            {"$match": {"device_id": device_id}},
            {"$sort": {"timestamp": 1}}
        ]
        records = list(db[coll].aggregate(pipeline))
        df = pd.DataFrame(records)
        if not df.empty:
            df = df.drop(columns=["_id"], errors="ignore")
            col_name = f"{coll.replace('-', '_')}"
            df[col_name] = df.get("device_pin_value")
            if "timestamp" in df.columns:
                df = df[["timestamp", col_name]]
            else:
                df = df.reset_index(drop=True)
                df.index.name = "row_index"
                df = df.reset_index()[["row_index", col_name]]
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    df_merged = dfs[0]
    for df in dfs[1:]:
        merge_col = "timestamp" if "timestamp" in df.columns else "row_index"
        df_merged = pd.merge(df_merged, df, on=merge_col, how="outer")
    df_merged.sort_values(by=df_merged.columns[0], inplace=True)
    return df_merged

def export_dataframe_to_excel(df):
    if df is None or df.empty:
        return Response("No data to export.", mimetype="text/plain")
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment;filename=export.xlsx"}
    )

# Initialize Dash app
from server import server
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], server=server)
app.title = "CGF Device Dashboard"

# App Layout
app.layout = dbc.Container(
    fluid=True,
    children=[
        html.Br(),
        html.H2("CGF System Metrics Dashboard", className="text-center mb-4"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(
                id="device-input",
                options=[{"label": did, "value": did} for did in get_device_ids()],
                placeholder="Select Device ID",
                clearable=False
            ), width=4),
            dbc.Col(dbc.Button("Export to Excel", id="export-btn", color="success", n_clicks=0), width=2)
        ], className="mb-4 justify-content-between"),
        # Summary Cards
        dbc.Row([
            dbc.Col(dbc.Card([html.Div([html.Strong("Plant Efficiency"), html.Div(id="plant-efficiency")])]), width=3),
            dbc.Col(dbc.Card([html.Div([html.Strong("Methane Concentration"), html.Div(id="methane-conc")])]), width=3),
            dbc.Col(dbc.Card([html.Div([html.Strong("Gas Yesterday"), html.Div(id="gas-yesterday")])]), width=3),
            dbc.Col(dbc.Card([html.Div([html.Strong("Gas Today"), html.Div(id="gas-today")])]), width=3)
        ], className="mb-4 g-3"),
        # Info Tiles
        dbc.Row([
            dbc.Col(dbc.Card([html.Div([html.Strong("Live Gas Flow"), html.Div(id="live-gas-flow")])]), width=3),
            dbc.Col(dbc.Card([html.Div([html.Strong("Total Gas"), html.Div(id="total-gas")])]), width=3),
            dbc.Col(dbc.Card([html.Div([html.Strong("Battery Charged"), html.Div(id="battery-charged")])]), width=3),
            dbc.Col(dbc.Card([html.Div([html.Strong("Temperature"), html.Div(id="temperature")])]), width=3)
        ], className="mb-4 g-3"),
        # Gas Production Graph
        dbc.Card([
            dbc.CardHeader(html.H5("Daily Gas Production (last 90 days)")),
            dbc.CardBody(dcc.Graph(id="gas-production-graph"))
        ], className="mb-4"),
        # Device Data Table
        dbc.Card([
            dbc.CardHeader(html.H5("Device Data")),
            dbc.CardBody(html.Div(id="device-data-table"))
        ])
    ]
)

# Callbacks
@app.callback(
    Output("plant-efficiency", "children"),
    Input("device-input", "value")
)
def update_plant_eff(device_id):
    if not device_id:
        return "-"
    metrics = fetch_latest_metrics(device_id)
    val = float(metrics.get("gas-flow-oc", {}).get("device_pin_value", 0)) * 1.2
    return f"{val:.1f}%"

@app.callback(
    Output("methane-conc", "children"),
    Input("device-input", "value")
)
def update_methane(device_id):
    if not device_id:
        return "-"
    metrics = fetch_latest_metrics(device_id)
    val = float(metrics.get("methane-conc", {}).get("device_pin_value", 0))
    return f"{val:.1f}%"

@app.callback(
    [Output("gas-yesterday", "children"), Output("gas-today", "children")],
    Input("device-input", "value")
)
def update_gas_days(device_id):
    if not device_id:
        return ["-","-"]
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    def sum_day(start, end):
        pipeline=[{"$match": {"device_id": device_id, "timestamp": {"$gte": start, "$lt": end}}},
                  {"$group": {"_id": None, "value": {"$sum": "$device_pin_value"}}}]
        res=list(db['gas-flow-oc'].aggregate(pipeline))
        return float(res[0]['value']) if res else 0
    t_start = datetime.combine(today, datetime.min.time())
    y_start = datetime.combine(yesterday, datetime.min.time())
    val_today = sum_day(t_start, t_start+timedelta(days=1))
    val_yest = sum_day(y_start, t_start)
    return [f"{val_yest:.2f} m³", f"{val_today:.2f} m³"]

@app.callback(
    [Output("live-gas-flow", "children"), Output("total-gas", "children")],
    Input("device-input", "value")
)
def update_live_total(device_id):
    if not device_id:
        return ["-","-"]
    metrics = fetch_latest_metrics(device_id)
    live = float(metrics.get("gas-flow-oc", {}).get("device_pin_value", 0))
    pipeline=[{"$match": {"device_id": device_id}}, {"$group": {"_id": None, "total": {"$sum": "$device_pin_value"}}}]
    res=list(db['gas-flow-oc'].aggregate(pipeline))
    total = float(res[0]['total']) if res else 0
    return [f"{live:.2f}", f"{total:.2f} m³"]

@app.callback(
    [Output("battery-charged", "children"), Output("temperature", "children")],
    Input("device-input", "value")
)
def update_batt_temp(device_id):
    if not device_id:
        return ["-","-"]
    metrics = fetch_latest_metrics(device_id)
    batt = float(metrics.get("battery-per", {}).get("device_pin_value", 0))
    temp = float(metrics.get("gas-temp", {}).get("device_pin_value", 0))
    return [f"{batt:.1f}%", f"{temp:.1f}°C"]

@app.callback(
    Output("gas-production-graph", "figure"),
    Input("device-input", "value")
)
def update_graph(device_id):
    fig = go.Figure()
    if not device_id:
        return fig
    df = fetch_gas_production_history(device_id, 90)
    if not df.empty:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["device_pin_value"], mode="lines+markers"))
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=340)
    return fig

@app.callback(
    Output("device-data-table", "children"),
    Input("device-input", "value")
)
def update_table(device_id):
    if not device_id:
        return dash_table.DataTable(data=[], columns=[])
    df = fetch_and_merge_data(device_id)
    if df.empty:
        return html.Div("No data available for this device")
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_size=10,
        style_table={"overflowX": "auto"},
        style_header={"fontWeight": "bold"}
    )

# Excel export route
@app.server.route("/download")
def download():
    device_id = dash.callback_context.request.args.get("device_id")
    if not device_id:
        return Response("No device selected.", mimetype="text/plain")
    df = fetch_gas_production_history(device_id, 90)
    return export_dataframe_to_excel(df)

if __name__ == "__main__":
    app.run(debug=True)
