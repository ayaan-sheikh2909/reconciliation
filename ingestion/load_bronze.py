from pathlib import Path

import dlt
import duckdb
import pandas as pd

ERP_FEED_PATH = Path("data/processed/feeds/erp_feed.parquet")
WMS_FEED_PATH = Path("data/processed/feeds/wms_feed.parquet")
WAREHOUSE_PATH = Path("data/warehouse/reconciliation.duckdb")


def print_load_info(label: str, load_info) -> None:
    print(f"\n{label} load info:")
    print(load_info)


def main():
    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)

    erp_df = pd.read_parquet(ERP_FEED_PATH)
    wms_df = pd.read_parquet(WMS_FEED_PATH)

    # one pipeline, one bronze dataset; each feed lands in its own table with its
    # own native schema - no renaming or unifying here, that's silver's job
    pipeline = dlt.pipeline(
        pipeline_name="reconciliation_bronze",
        destination=dlt.destinations.duckdb(str(WAREHOUSE_PATH)),
        dataset_name="bronze",
    )

    # merge on a real per-row key proves this load is idempotent: rerunning this
    # script against the same files must not duplicate warehouse rows
    erp_load_info = pipeline.run(
        erp_df,
        table_name="erp_feed",
        write_disposition="merge",
        primary_key=["erp_doc_number", "line_item_number"],
    )
    wms_load_info = pipeline.run(
        wms_df,
        table_name="wms_feed",
        write_disposition="merge",
        primary_key="row_id",
    )

    print_load_info("ERP feed", erp_load_info)
    print_load_info("WMS feed", wms_load_info)

    with duckdb.connect(str(WAREHOUSE_PATH)) as con:
        erp_count = con.sql("SELECT COUNT(*) FROM bronze.erp_feed").fetchone()[0]
        wms_count = con.sql("SELECT COUNT(*) FROM bronze.wms_feed").fetchone()[0]

        print(f"\nRow count in bronze.erp_feed: {erp_count}")
        print(f"Row count in bronze.wms_feed: {wms_count}")

        print("\nbronze.erp_feed columns:")
        print(con.sql("DESCRIBE bronze.erp_feed").df().to_string(index=False))

        print("\nbronze.wms_feed columns:")
        print(con.sql("DESCRIBE bronze.wms_feed").df().to_string(index=False))

    print(f"\nWrote bronze warehouse to {WAREHOUSE_PATH}")


if __name__ == "__main__":
    main()
