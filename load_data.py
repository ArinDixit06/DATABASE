# callbacks/load_data.py
from dash import dash_table
import dash_bootstrap_components as dbc
from database.mongo_handler import fetch_and_merge_data

# For external use by app.py to set this value globally
last_df = None

def register_callbacks(app):
    @app.callback(
        [Output("message-div", "children"),
         Output("table-div", "children")],
        [Input("load-button", "n_clicks")],
        [State("device-input", "value")]
    )
    def load_and_merge(n_clicks, device_id):
        global last_df
        if not n_clicks:
            return "", ""

        if not device_id:
            return dbc.Alert("Please select a device_id.", color="warning"), ""

        merged_df = fetch_and_merge_data(device_id)
        if merged_df is None or merged_df.empty:
            last_df = None
            return dbc.Alert(f"No data found for device_id '{device_id}'.", color="danger"), ""

        last_df = merged_df.copy()

        table = dash_table.DataTable(
            data=merged_df.to_dict("records"),
            columns=[{"name": col, "id": col} for col in merged_df.columns],
            page_size=1,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "minWidth": "100px"},
        )
        return "", table
