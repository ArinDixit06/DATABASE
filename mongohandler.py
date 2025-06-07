# database/mongo_handler.py
import pandas as pd
from config import db

collections = [
    "gas-flow-oc",
    "battery-per",
    "pressure",
    "volume-oc",
    "methane-conc",
    "gas-temp",
    "electric-current",
]

def get_device_ids():
    ids = set()
    for coll in collections:
        try:
            ids.update(db[coll].distinct("device_id"))
        except Exception:
            pass
    return sorted(ids)

def fetch_and_merge_data(device_id):
    merged_df = None

    for coll_name in collections:
        try:
            cursor = db[coll_name].find({"device_id": device_id}, limit=10000)
            records = list(cursor)

            if not records:
                continue

            df = pd.DataFrame(records)
            if df.empty:
                continue

            if "_id" in df.columns:
                df.drop(columns=["_id"], inplace=True)

            if "row_index" not in df.columns:
                df.reset_index(inplace=True)
                df.rename(columns={"index": "row_index"}, inplace=True)

            value_col = f"device_pin_value_{coll_name.replace('-', '_')}"
            if "device_pin_value" in df.columns:
                df.rename(columns={"device_pin_value": value_col}, inplace=True)
            else:
                df[value_col] = pd.NA

            columns_to_keep = ["row_index", value_col]
            if "device_name" in df.columns:
                columns_to_keep.append("device_name")

            df = df[columns_to_keep]

            if merged_df is None:
                merged_df = df
            else:
                merged_df = pd.merge(
                    merged_df,
                    df.drop(columns=["device_name"], errors="ignore"),
                    on="row_index",
                    how="outer"
                )

        except Exception as e:
            print(f"Error processing collection {coll_name}: {e}")
            continue

    if merged_df is not None and not merged_df.empty:
        merged_df = merged_df[merged_df["row_index"] == 0].reset_index(drop=True)
        if "device_name" in merged_df.columns:
            cols = ["device_name"] + [c for c in merged_df.columns if c != "device_name"]
            merged_df = merged_df[cols]

    return merged_df


