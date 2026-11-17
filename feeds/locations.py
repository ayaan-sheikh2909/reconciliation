import hashlib # for using the md5 hash function

import numpy as np #performing array arithmetic operations
import pandas as pd # for handling dataframes and series

WAREHOUSE_CODES = ["WH-01", "WH-02", "WH-03", "WH-04"] # list of warehouse codes
BIN_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" # possible letters for bin locations
BIN_DIGITS = "123456789" # possible digits for bin locations


def _md5_int(values: pd.Series) -> np.ndarray: # convert series of strings to array of uint64 md5 hashes
    # stable, deterministic hash per string value -> unsigned int, independent of
    # Python's randomized string hashing (which varies across runs/processes).
    # Truncate the 128-bit (32 hex chars) md5 digest to its first 16 hex chars (64 bits) so it
    # fits in a uint64.
    return np.array(
        [int(hashlib.md5(v.encode("utf-8")).hexdigest()[:16], 16) for v in values],
        dtype=np.uint64,
    )


def assign_warehouse(stock_code: pd.Series) -> pd.Series:
    digest = _md5_int(stock_code.astype(str)) # get the md5 hash as uint64 array for the stock codes
    idx = digest % len(WAREHOUSE_CODES) # get the index of the warehouse code for each stock code based on the hash
    return pd.Series(np.array(WAREHOUSE_CODES)[idx], index=stock_code.index, name="warehouse_code") # return the warehouse code series based on the computed indices


def assign_bin(stock_code: pd.Series, warehouse_code: pd.Series) -> pd.Series:
    combined = stock_code.astype(str) + "|" + warehouse_code.astype(str)
    digest = _md5_int(combined)
    letter1 = np.array(list(BIN_LETTERS))[digest % len(BIN_LETTERS)]
    digit1 = np.array(list(BIN_DIGITS))[(digest // len(BIN_LETTERS)) % len(BIN_DIGITS)]
    letter2 = np.array(list(BIN_LETTERS))[(digest // (len(BIN_LETTERS) * len(BIN_DIGITS))) % len(BIN_LETTERS)]
    digit2 = np.array(list(BIN_DIGITS))[
        (digest // (len(BIN_LETTERS) * len(BIN_DIGITS) * len(BIN_LETTERS))) % len(BIN_DIGITS)
    ]
    bins = np.char.add(np.char.add(np.char.add(letter1, digit1), "-"), np.char.add(letter2, digit2))
    return pd.Series(bins, index=stock_code.index, name="bin_location")


