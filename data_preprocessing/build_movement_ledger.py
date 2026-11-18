# import systems to stop execution if input file is missing, pathlib to get paths and pandas to read xls file and create dataframe
import sys
from pathlib import Path
import pandas as pd


RAW_PATH = Path("data/raw/online_retail_II.xlsx")
LEDGER_PATH = Path("data/processed/movement_ledger.parquet")
EXCLUSIONS_PATH = Path("data/processed/evaluation/exclusions_report.csv")
# Define paths for raw input, processed ledger, and exclusions report using the pathlib library

SHEETS = ["Year 2009-2010", "Year 2010-2011"]
# Define the sheets to read from the raw Excel file

EXACT_EXCLUDED_CODES = {
    "POST",
    "DOT",
    "C2",
    "D",
    "S",
    "M",
    "m",
    "BANK CHARGES",
    "B",
    "ADJUST",
    "AMAZONFEE",
    "TEST001",
    "CRUK",
}
# Define exact stock codes to exclude from the ledger
# Define prefix for gift card stock codes to exclude from the ledger
GIFT_PREFIX = "gift_0001"

COLUMN_RENAME = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "price",
    "Customer ID": "customer_id",
    "Country": "country",
}
# Define column renaming mapping for consistency in the ledger by converting to snake_case

def main():
    if not RAW_PATH.exists():
        print(f"Missing input file: {RAW_PATH} — stopping.")
        sys.exit(1)
        # Stop execution if the raw input file is missing

    frames = [] # initialize list to hold dataframes from each sheet
    for sheet in SHEETS:
        sheet_df = pd.read_excel(RAW_PATH, sheet_name=sheet)
        sheet_df["source_sheet"] = sheet # add a column to track the source sheet
        frames.append(sheet_df)

    df = pd.concat(frames, ignore_index=True) # concatenate all sheet dataframes into a single dataframe

    df = df.rename(columns=COLUMN_RENAME) # rename columns for consistency in the ledger

    total_before = len(df) # store the total number of rows before exclusions so we can verify the number of rows removed later

    stock_code_str = df["stock_code"].astype(str) # convert stock_code column to string for consistent comparison
    is_excluded = stock_code_str.isin(EXACT_EXCLUDED_CODES) | stock_code_str.str.startswith(GIFT_PREFIX) # comparison logic for excl

    exclusions = (
        df.loc[is_excluded, "stock_code"] # get the stock codes that are excluded, along with indexes from the original dataframe
        .astype(str) # ensure the excluded stock codes and other values are treated as strings
        .value_counts() # count the number of excluded rows per stock code, this replaces the existing index with the counts as the new index
        .rename_axis("stock_code") # set the name of the index to 'stock_code' for clarity in the resulting dataframe
        .reset_index(name="excluded_row_count") # reset the index to turn the stock_code index into a column and name the count column
        .sort_values("excluded_row_count", ascending=False) # sort the exclusions by the number of excluded rows in descending order
    )
    EXCLUSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    exclusions.to_csv(EXCLUSIONS_PATH, index=False)

    print("Rows excluded per stock_code:")
    print(exclusions.to_string(index=False))
    print(f"Saved exclusions report to {EXCLUSIONS_PATH}")

    df = df.loc[~is_excluded].copy() # keep only the rows that are not excluded
    total_after = len(df) # store the total number of rows after exclusions for reporting purposes

    is_return = df["invoice"].astype(str).str.startswith("C") # identify rows that are returns based on the invoice starting with 'C' condition
    is_write_off = (~is_return) & (df["quantity"] < 0) #identify rows that are write-offs based on negative quantity and not being a return condition
    df["movement_type"] = "sale" # default movement type is 'sale', will be updated for returns and write-offs
    df.loc[is_write_off, "movement_type"] = "write_off" # check condition for write-offs and update movement_type accordingly
    df.loc[is_return, "movement_type"] = "return" # check condition for returns and update movement_type accordingly

    df["movement_qty"] = -df["quantity"] # the original sheet records outgoing movement as positive quantity for sales and negative for returns, so we invert it to represent movement quantity correctly
    df.loc[is_write_off, "movement_qty"] = df.loc[is_write_off, "quantity"]
    # for write-offs, the movement quantity should reflect the actual negative quantity, so we override the previous inversion for these rows

    # typecasting to ensure correct data types for further processing and analysis
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    df["stock_code"] = df["stock_code"].astype(str)
    df["invoice"] = df["invoice"].astype(str)
    df["description"] = df["description"].where(df["description"].isna(), df["description"].astype(str)) # conditionally convert description to string, keeping true nulls as null

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(LEDGER_PATH, index=False)

    print(f"\nTotal rows before exclusion: {total_before}")
    print(f"Total rows after exclusion:  {total_after}")
    print("\nmovement_type counts:")
    print(df["movement_type"].value_counts().to_string())
    print(f"\nDate range covered: {df['invoice_date'].min()} to {df['invoice_date'].max()}")
    print(f"\nWrote movement ledger to {LEDGER_PATH}")


if __name__ == "__main__":
    main()
