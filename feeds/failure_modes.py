import numpy as np
import pandas as pd

from feeds import locations

# internal bookkeeping column: marks rows already claimed by an earlier failure
# mode this run, so later modes sample only from untouched rows. Dropped before
# the corrupted df is returned from apply_all_failure_modes.
_TOUCHED_COL = "_touched"


def _ensure_bookkeeping(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "row_id" not in df.columns:
        df["row_id"] = np.arange(len(df))
    if _TOUCHED_COL not in df.columns:
        df[_TOUCHED_COL] = False
    return df


def _empty_log() -> pd.DataFrame:
    return pd.DataFrame(columns=["row_id", "failure_mode", "field_changed", "old_value", "new_value"])


def apply_unit_of_measure_divergence(
    df: pd.DataFrame, rng: np.random.Generator, rate: float = 0.01
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _ensure_bookkeeping(df)
    eligible = df.index[(df["event_type"] == "sale") & (~df[_TOUCHED_COL])]
    n = round(rate * len(eligible))
    if n == 0:
        return df, _empty_log()

    sampled_idx = rng.choice(eligible.to_numpy(), size=n, replace=False)
    case_pack = rng.choice([6, 12], size=n)
    old_values = df.loc[sampled_idx, "units"].to_numpy()
    new_values = old_values * case_pack

    log = pd.DataFrame(
        {
            "row_id": df.loc[sampled_idx, "row_id"].to_numpy(),
            "failure_mode": "unit_of_measure_divergence",
            "field_changed": "units",
            "old_value": old_values,
            "new_value": new_values,
        }
    )
    df.loc[sampled_idx, "units"] = new_values
    df.loc[sampled_idx, _TOUCHED_COL] = True
    return df, log


def apply_posting_lag(
    df: pd.DataFrame, rng: np.random.Generator, rate: float = 0.02
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _ensure_bookkeeping(df)
    eligible = df.index[~df[_TOUCHED_COL]]
    n = round(rate * len(eligible))
    if n == 0:
        return df, _empty_log()

    sampled_idx = rng.choice(eligible.to_numpy(), size=n, replace=False)
    shift_days = rng.integers(1, 6, size=n)  # 1-5 inclusive
    old_values = df.loc[sampled_idx, "event_date"].to_numpy()
    new_values = df.loc[sampled_idx, "event_date"] + pd.to_timedelta(shift_days, unit="D")

    log = pd.DataFrame(
        {
            "row_id": df.loc[sampled_idx, "row_id"].to_numpy(),
            "failure_mode": "posting_lag",
            "field_changed": "event_date",
            "old_value": old_values,
            "new_value": new_values.to_numpy(),
        }
    )
    df.loc[sampled_idx, "event_date"] = new_values
    df.loc[sampled_idx, _TOUCHED_COL] = True
    return df, log


def apply_dropped_return(
    df: pd.DataFrame, rng: np.random.Generator, rate: float = 0.05
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _ensure_bookkeeping(df)
    eligible = df.index[(df["event_type"] == "return") & (~df[_TOUCHED_COL])]
    n = round(rate * len(eligible))
    if n == 0:
        return df, _empty_log()

    sampled_idx = rng.choice(eligible.to_numpy(), size=n, replace=False)

    log = pd.DataFrame(
        {
            "row_id": df.loc[sampled_idx, "row_id"].to_numpy(),
            "failure_mode": "dropped_return",
            "field_changed": "row",
            "old_value": "present",
            "new_value": "dropped",
        }
    )
    df = df.drop(index=sampled_idx)
    return df, log


def apply_duplicate_movement(
    df: pd.DataFrame, rng: np.random.Generator, rate: float = 0.005
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _ensure_bookkeeping(df)
    eligible = df.index[(df["event_type"] == "sale") & (~df[_TOUCHED_COL])]
    n = round(rate * len(eligible))
    if n == 0:
        return df, _empty_log()

    sampled_idx = rng.choice(eligible.to_numpy(), size=n, replace=False)
    duplicates = df.loc[sampled_idx].copy()
    next_row_id = df["row_id"].max() + 1
    next_wms_event_id = df["wms_event_id"].max() + 1
    duplicates["row_id"] = np.arange(next_row_id, next_row_id + n)
    duplicates["wms_event_id"] = np.arange(next_wms_event_id, next_wms_event_id + n)
    duplicates[_TOUCHED_COL] = True

    log = pd.DataFrame(
        {
            "row_id": df.loc[sampled_idx, "row_id"].to_numpy(),
            "failure_mode": "duplicate_movement",
            "field_changed": "row",
            "old_value": "single",
            "new_value": duplicates["row_id"].to_numpy(),
        }
    )
    df.loc[sampled_idx, _TOUCHED_COL] = True
    df = pd.concat([df, duplicates], ignore_index=True)
    return df, log


def apply_sku_case_variant(
    df: pd.DataFrame, rng: np.random.Generator, rate: float = 0.01
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _ensure_bookkeeping(df)
    eligible = df.index[~df[_TOUCHED_COL]]
    n = round(rate * len(eligible))
    if n == 0:
        return df, _empty_log()

    sampled_idx = rng.choice(eligible.to_numpy(), size=n, replace=False)
    old_values = df.loc[sampled_idx, "sku"].to_numpy()
    case_choice = rng.integers(0, 3, size=n)  # 0=upper, 1=lower, 2=mixed (alternating)

    def recase(value: str, choice: int) -> str:
        if choice == 0:
            return value.upper()
        if choice == 1:
            return value.lower()
        return "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(value))

    new_values = np.array([recase(v, c) for v, c in zip(old_values, case_choice)])

    log = pd.DataFrame(
        {
            "row_id": df.loc[sampled_idx, "row_id"].to_numpy(),
            "failure_mode": "sku_case_variant",
            "field_changed": "sku",
            "old_value": old_values,
            "new_value": new_values,
        }
    )
    df.loc[sampled_idx, "sku"] = new_values
    df.loc[sampled_idx, _TOUCHED_COL] = True
    return df, log


def apply_manual_edit_injection(
    df: pd.DataFrame, rng: np.random.Generator, n: int = 50
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _ensure_bookkeeping(df)
    if n == 0:
        return df, _empty_log()

    sampled_skus = pd.Series(rng.choice(df["sku"].unique(), size=n, replace=True))
    warehouse_code = locations.assign_warehouse(sampled_skus)
    bin_location = locations.assign_bin(sampled_skus, warehouse_code)
    units = rng.integers(1, 6, size=n)  # 1-5 inclusive

    date_min, date_max = df["event_date"].min(), df["event_date"].max()
    span_seconds = (date_max - date_min).total_seconds()
    random_offsets = pd.to_timedelta(rng.random(n) * span_seconds, unit="s")
    event_date = date_min + random_offsets

    next_row_id = df["row_id"].max() + 1
    new_row_ids = np.arange(next_row_id, next_row_id + n)

    new_rows = pd.DataFrame(
        {
            "row_id": new_row_ids,
            "wms_event_id": new_row_ids,
            "sku": sampled_skus.to_numpy(),
            "warehouse_code": warehouse_code.to_numpy(),
            "bin_location": bin_location.to_numpy(),
            "units": units,
            "event_type": "manual_adjustment",
            "event_date": event_date,
            _TOUCHED_COL: True,
        }
    )

    log = pd.DataFrame(
        {
            "row_id": new_row_ids,
            "failure_mode": "manual_edit_injection",
            "field_changed": "row",
            "old_value": None,
            "new_value": "inserted",
        }
    )
    df = pd.concat([df, new_rows], ignore_index=True)
    return df, log


def apply_all_failure_modes(df: pd.DataFrame, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    df = _ensure_bookkeeping(df)

    logs = []
    df, log = apply_unit_of_measure_divergence(df, rng)
    logs.append(log)
    df, log = apply_posting_lag(df, rng)
    logs.append(log)
    df, log = apply_dropped_return(df, rng)
    logs.append(log)
    df, log = apply_duplicate_movement(df, rng)
    logs.append(log)
    df, log = apply_sku_case_variant(df, rng)
    logs.append(log)
    df, log = apply_manual_edit_injection(df, rng)
    logs.append(log)

    ground_truth = pd.concat(logs, ignore_index=True)
    # old_value/new_value carry ints, timestamps, and strings depending on the
    # failure mode; normalize both to strings (preserving true nulls) so the
    # log has one consistent, parquet-writable dtype per column.
    for col in ("old_value", "new_value"):
        ground_truth[col] = ground_truth[col].where(ground_truth[col].isna(), ground_truth[col].astype(str))
    df = df.drop(columns=[_TOUCHED_COL])
    return df, ground_truth
