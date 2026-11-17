from pathlib import Path

import numpy as np
import pandas as pd

from feeds import failure_modes, locations

LEDGER_PATH = Path("data/processed/movement_ledger.parquet")
WMS_FEED_PATH = Path("data/processed/wms_feed.parquet")
GROUND_TRUTH_PATH = Path("data/processed/drift_ground_truth.parquet")

COLUMN_RENAME = {
    "stock_code": "sku",
    "movement_type": "event_type",
    "movement_qty": "units",
    "invoice_date": "event_date",
}
DROP_COLUMNS = ["description", "price", "customer_id", "country", "source_sheet", "quantity", "invoice"]


def main():
    df = pd.read_parquet(LEDGER_PATH)

    warehouse_code = locations.assign_warehouse(df["stock_code"])
    bin_location = locations.assign_bin(df["stock_code"], warehouse_code)
    df["warehouse_code"] = warehouse_code
    df["bin_location"] = bin_location

    df["row_id"] = np.arange(len(df))
    df["wms_event_id"] = df["row_id"]

    df = df.drop(columns=DROP_COLUMNS).rename(columns=COLUMN_RENAME)

    total_before = len(df)
    corrupted_df, ground_truth_df = failure_modes.apply_all_failure_modes(df, seed=42)
    total_after = len(corrupted_df)

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
