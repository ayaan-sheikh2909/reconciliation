from pathlib import Path

import pandas as pd

from feeds import locations

LEDGER_PATH = Path("data/processed/movement_ledger.parquet")
ERP_FEED_PATH = Path("data/processed/erp_feed.parquet")

COLUMN_RENAME = {
    "invoice": "erp_doc_number",
    "stock_code": "item_code",
    "description": "item_description",
    "movement_type": "doc_type",
    "movement_qty": "qty_delta",
    "invoice_date": "posting_date",
}
DROP_COLUMNS = ["price", "customer_id", "country", "source_sheet", "quantity"]


def main():
    df = pd.read_parquet(LEDGER_PATH)

    df["warehouse_code"] = locations.assign_warehouse(df["stock_code"])

    df = df.drop(columns=DROP_COLUMNS).rename(columns=COLUMN_RENAME)

    ERP_FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ERP_FEED_PATH, index=False)

    print(f"Total rows: {len(df)}")
    print("\ndoc_type counts:")
    print(df["doc_type"].value_counts().to_string())
    print(f"\nDate range covered: {df['posting_date'].min()} to {df['posting_date'].max()}")
    print(f"\nWrote ERP feed to {ERP_FEED_PATH}")


if __name__ == "__main__":
    main()
