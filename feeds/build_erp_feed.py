from pathlib import Path # to import Path for file paths

import pandas as pd # to work with series and dataframes

from feeds import locations # to assign warehouse codes based on stock codes

LEDGER_PATH = Path("data/processed/movement_ledger.parquet") # then read the movement ledger from this path
ERP_FEED_PATH = Path("data/processed/feeds/erp_feed.parquet") # path to write the ERP feed to

# in real world scenarios, the erp and wms have diffferent column names and formats, so we need to rename and drop columns accordingly 
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
    df = pd.read_parquet(LEDGER_PATH) # read the original movement ledger

    df["warehouse_code"] = locations.assign_warehouse(df["stock_code"]) # assign warehouse codes based on stock codes

    df = df.drop(columns=DROP_COLUMNS).rename(columns=COLUMN_RENAME) # drop unnecessary columns and rename for ERP feed

    # a real ERP numbers each document's lines (header + line = the true composite key,
    # e.g. SAP material documents); derive that here rather than faking a row id at ingestion
    df["line_item_number"] = df.groupby("erp_doc_number").cumcount() + 1

    ERP_FEED_PATH.parent.mkdir(parents=True, exist_ok=True) # check and create the parent directory if it doesn't exist
    df.to_parquet(ERP_FEED_PATH, index=False) # write the ERP feed to the specified path

    print(f"Total rows: {len(df)}") # print the total number of rows in the ERP feed
    print("\ndoc_type counts:") # print the counts of each document type
    print(df["doc_type"].value_counts().to_string())
    print(f"\nDate range covered: {df['posting_date'].min()} to {df['posting_date'].max()}") # print the date range covered by the ERP feed
    print(f"\nWrote ERP feed to {ERP_FEED_PATH}") # print the path where the ERP feed was written   


if __name__ == "__main__":
    main()
