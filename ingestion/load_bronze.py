from pathlib import Path # to handle file paths and load the erp and wms feeds

import dlt # for data extraction and loading into the warehouse
import duckdb # duckdb is local SQL OLAP database engine
import pandas as pd # for handling dataframes and reading parquet files

ERP_FEED_PATH = Path("data/processed/feeds/erp_feed.parquet") # path to the processed ERP feed parquet file
WMS_FEED_PATH = Path("data/processed/feeds/wms_feed.parquet") # path to the processed WMS feed parquet file
WAREHOUSE_PATH = Path("data/warehouse/reconciliation.duckdb") # path to the local DuckDB warehouse file


def print_load_info(label: str, load_info) -> None:
    print(f"\n{label} load info:")
    print(load_info)


def main():
    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True) # create the warehouse directory if it doesn't exist

    erp_df = pd.read_parquet(ERP_FEED_PATH) # read the ERP feed parquet file into a dataframe
    wms_df = pd.read_parquet(WMS_FEED_PATH) # read the WMS feed parquet file into a dataframe

    # one pipeline, one bronze dataset; each feed lands in its own table with its
    # own native schema - no renaming or unifying here, that's silver's job
    pipeline = dlt.pipeline(
        pipeline_name="reconciliation_bronze", # name of the DLT pipeline
        destination=dlt.destinations.duckdb(str(WAREHOUSE_PATH)), # set the destination to the local DuckDB warehouse file
        dataset_name="bronze", # name of the dataset within the DLT pipeline
    )

    # merge on a real per-row key proves this load is idempotent: rerunning this
    # script against the same files must not duplicate warehouse rows
    # run the pipeline for the ERP and WMS feeds, merging on the primary keys to ensure idempotency
    erp_load_info = pipeline.run(
        erp_df,
        table_name="erp_feed",
        write_disposition="merge", # used for mainly updating existing rows based on the primary key and inserting new ones
        primary_key=["erp_doc_number", "line_item_number"], # used composite key to uniquely identify each row in the ERP feed as erp_doc_number are not unique by themselves
    )
    wms_load_info = pipeline.run(
        wms_df,
        table_name="wms_feed",
        write_disposition="merge", # used for mainly updating existing rows based on the primary key and inserting new ones
        primary_key="row_id",
    )

    print_load_info("ERP feed", erp_load_info) # print the load info for the ERP feed
    print_load_info("WMS feed", wms_load_info) # print the load info for the WMS feed

    with duckdb.connect(str(WAREHOUSE_PATH)) as con:
        erp_count = con.sql("SELECT COUNT(*) FROM bronze.erp_feed").fetchone()[0] # get the row count for the ERP feed
        wms_count = con.sql("SELECT COUNT(*) FROM bronze.wms_feed").fetchone()[0] # get the row count for the WMS feed

        print(f"\nRow count in bronze.erp_feed: {erp_count}")
        print(f"Row count in bronze.wms_feed: {wms_count}")

        print("\nbronze.erp_feed columns:")
        print(con.sql("DESCRIBE bronze.erp_feed").df().to_string(index=False))

        print("\nbronze.wms_feed columns:")
        print(con.sql("DESCRIBE bronze.wms_feed").df().to_string(index=False))

    print(f"\nWrote bronze warehouse to {WAREHOUSE_PATH}")


if __name__ == "__main__":
    main()
  
