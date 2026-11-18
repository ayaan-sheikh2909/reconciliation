from pathlib import Path # for handling file paths and loading parquet files

import numpy as np # for numerical operations
import pandas as pd # for using DataFrames and reading/writing parquet files

from feeds import failure_modes, locations # for applying failure modes and assigning warehouse/bin locations

LEDGER_PATH = Path("data/processed/movement_ledger.parquet")
WMS_FEED_PATH = Path("data/processed/feeds/wms_feed.parquet")
GROUND_TRUTH_PATH = Path("data/processed/evaluation/drift_ground_truth.parquet")

# Define column renaming and columns to drop for the WMS feed as done with ERP feed , more stock movement based
COLUMN_RENAME = {
    "stock_code": "sku",
    "description": "item_desc",
    "movement_type": "event_type",
    "movement_qty": "units",
    "invoice_date": "event_date",
}
DROP_COLUMNS = ["price", "customer_id", "country", "source_sheet", "quantity", "invoice"]


def main():
    df = pd.read_parquet(LEDGER_PATH) # load the movement ledger parquet file into a DataFrame

    warehouse_code = locations.assign_warehouse(df["stock_code"]) # assign warehouse codes based on stock codes
    bin_location = locations.assign_bin(df["stock_code"], warehouse_code) # assign bin locations based on stock codes and warehouse codes
    df["warehouse_code"] = warehouse_code # add warehouse codes to the DataFrame
    df["bin_location"] = bin_location # add bin locations to the DataFrame
    

    df["row_id"] = np.arange(len(df)) # when failures modes will be applied the index of each row will be tracked using this row_id


    df = df.drop(columns=DROP_COLUMNS).rename(columns=COLUMN_RENAME) # drop unnecessary columns and rename columns for WMS feed

    total_before = len(df) # store the total number of rows before applying failure modes
    corrupted_df, ground_truth_df = failure_modes.apply_all_failure_modes(df, seed=42) # apply all defined failure modes to the DataFrame
    total_after = len(corrupted_df) # store the total number of rows after applying failure modes

    WMS_FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    corrupted_df.to_parquet(WMS_FEED_PATH, index=False)
    ground_truth_df.to_parquet(GROUND_TRUTH_PATH, index=False)

    print(f"Total rows before corruption: {total_before}")
    print(f"Total rows after corruption:  {total_after}")

    print("\nRows affected per failure_mode:")
    print(ground_truth_df["failure_mode"].value_counts().to_string())

    print("\nevent_type counts:")
    print(corrupted_df["event_type"].value_counts().to_string())

    print(f"\nDate range covered: {corrupted_df['event_date'].min()} to {corrupted_df['event_date'].max()}")
    print(f"\nWrote WMS feed to {WMS_FEED_PATH}")
    print(f"Wrote drift ground truth to {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
