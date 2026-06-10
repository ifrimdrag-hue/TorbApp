"""Weekly series extraction from tranzactii.

Weeks are ISO Mondays. Series IDs follow the statsforecast convention
(unique_id, ds, y).

Public functions:
    weekly_brand_channel(furnizor=None) -> DataFrame
    weekly_sku_channel(cod_produs_list=None, furnizor=None) -> DataFrame
    sku_mix_recent(furnizor, weeks=12) -> DataFrame with brand-channel allocation share
    sku_catalog(furnizor=None) -> DataFrame (cod_produs, sku, furnizor, first_seen, last_seen, total_qty, total_val)
"""

import os
import sqlite3
import pandas as pd

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "torb.db",
)


def _connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_canal(s):
    if s is None:
        return "ALTELE"
    s = str(s).strip().upper()
    # Canonicalize the data's inconsistencies.
    mapping = {
        "FARA TIP CLIENT": "ALTELE",
        "ALTI": "ALTELE",
        "DISTRUBUITOR PHARMA": "PHARMA",
        "FARMACIE": "PHARMA",
        "DISTRIBUITOR FOOD": "DISTRIBUITOR",
        "HYPERMARKET": "HYPERMARKET",
        "SUPERMARKET": "SUPERMARKET",
        "BENZINARIE MOL": "ALTELE",
    }
    return mapping.get(s, s)


def _fill_weekly_gaps(df, min_ds=None, max_ds=None):
    """Ensure every series has a row for every week in [min_ds, max_ds].

    df must have columns (unique_id, ds, y, val_neta).
    Returns df with 0 inserted for missing weeks.
    """
    if df.empty:
        return df

    if min_ds is None:
        min_ds = df["ds"].min()
    if max_ds is None:
        max_ds = df["ds"].max()

    all_weeks = pd.date_range(start=min_ds, end=max_ds, freq="W-MON")
    series_ids = df["unique_id"].unique()

    idx = pd.MultiIndex.from_product(
        [series_ids, all_weeks], names=["unique_id", "ds"]
    )
    full = pd.DataFrame(index=idx).reset_index()

    merged = full.merge(df, on=["unique_id", "ds"], how="left")
    merged["y"] = merged["y"].fillna(0)
    merged["val_neta"] = merged["val_neta"].fillna(0)

    # Preserve static columns (furnizor, canal) via forward/back fill within series
    for col in ("furnizor", "canal", "cod_produs", "sku"):
        if col in merged.columns:
            merged[col] = merged.groupby("unique_id")[col].transform(
                lambda s: s.ffill().bfill()
            )

    return merged.sort_values(["unique_id", "ds"]).reset_index(drop=True)


def weekly_brand_channel(furnizor=None, min_year=2024, db_path=DB_PATH):
    """Weekly (quantity, val_neta) per brand × canal.

    Returns DataFrame with columns:
        unique_id (brand|canal), ds (Monday), y (units), val_neta (RON),
        furnizor, canal.
    """
    sql = """
        SELECT
            DATE(data_dl, 'weekday 0', '-6 days') AS ds,
            furnizor,
            tip_client AS canal_raw,
            SUM(cantitate) AS y,
            SUM(val_neta) AS val_neta
        FROM tranzactii
        WHERE an >= :min_year
          AND data_dl IS NOT NULL
          AND furnizor IS NOT NULL
    """
    params = {"min_year": min_year}
    if furnizor:
        sql += " AND furnizor = :furnizor"
        params["furnizor"] = furnizor
    sql += " GROUP BY ds, furnizor, canal_raw"

    with _connect(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    df["canal"] = df["canal_raw"].map(_normalize_canal)
    df = df.drop(columns=["canal_raw"])
    df["ds"] = pd.to_datetime(df["ds"])

    # Aggregate after canal normalization (mapping collapses multiple raw types).
    df = (
        df.groupby(["ds", "furnizor", "canal"], as_index=False)
          .agg(y=("y", "sum"), val_neta=("val_neta", "sum"))
    )
    df["unique_id"] = df["furnizor"] + "|" + df["canal"]
    df = df[["unique_id", "ds", "y", "val_neta", "furnizor", "canal"]]

    return _fill_weekly_gaps(df)


def weekly_sku_channel(furnizor=None, cod_produs_list=None,
                       min_year=2024, db_path=DB_PATH):
    """Weekly units per SKU × canal.

    Returns DataFrame (unique_id=cod_produs|canal, ds, y, val_neta,
    cod_produs, sku, furnizor, canal).
    """
    sql = """
        SELECT
            DATE(data_dl, 'weekday 0', '-6 days') AS ds,
            cod_produs, sku, furnizor,
            tip_client AS canal_raw,
            SUM(cantitate) AS y,
            SUM(val_neta) AS val_neta
        FROM tranzactii
        WHERE an >= :min_year
          AND data_dl IS NOT NULL
          AND cod_produs IS NOT NULL
          AND furnizor IS NOT NULL
    """
    params = {"min_year": min_year}
    if furnizor:
        sql += " AND furnizor = :furnizor"
        params["furnizor"] = furnizor
    if cod_produs_list:
        placeholders = ",".join(f":c{i}" for i in range(len(cod_produs_list)))
        sql += f" AND cod_produs IN ({placeholders})"
        for i, c in enumerate(cod_produs_list):
            params[f"c{i}"] = c
    sql += " GROUP BY ds, cod_produs, sku, furnizor, canal_raw"

    with _connect(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    df["canal"] = df["canal_raw"].map(_normalize_canal)
    df = df.drop(columns=["canal_raw"])
    df["ds"] = pd.to_datetime(df["ds"])

    df = (
        df.groupby(["ds", "cod_produs", "sku", "furnizor", "canal"], as_index=False)
          .agg(y=("y", "sum"), val_neta=("val_neta", "sum"))
    )
    df["unique_id"] = df["cod_produs"].astype(str) + "|" + df["canal"]
    df = df[["unique_id", "ds", "y", "val_neta",
             "cod_produs", "sku", "furnizor", "canal"]]

    return _fill_weekly_gaps(df)


def sku_mix_recent(furnizor, weeks=12, as_of=None, db_path=DB_PATH):
    """Share of each SKU × canal inside its brand × canal, trailing N weeks.

    Returns DataFrame (cod_produs, sku, furnizor, canal, share).
    Shares sum to ~1.0 within each (furnizor, canal) group.
    Used for middle-out allocation: brand forecast × share = SKU forecast.
    """
    days = weeks * 7
    if as_of is None:
        as_of_sql = "(SELECT MAX(data_dl) FROM tranzactii)"
        params = {"furnizor": furnizor, "days": days}
    else:
        as_of_sql = ":as_of"
        params = {"furnizor": furnizor, "days": days, "as_of": as_of}

    sql = f"""
        WITH cutoff AS (
            SELECT DATE({as_of_sql}, '-' || :days || ' days') AS d
        )
        SELECT cod_produs, sku, furnizor, tip_client AS canal_raw,
               SUM(cantitate) AS qty
        FROM tranzactii
        WHERE furnizor = :furnizor
          AND data_dl > (SELECT d FROM cutoff)
          AND cantitate IS NOT NULL
        GROUP BY cod_produs, sku, furnizor, canal_raw
    """
    with _connect(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        return df.assign(canal=[], share=[])

    df["canal"] = df["canal_raw"].map(_normalize_canal)
    df = (
        df.groupby(["cod_produs", "sku", "furnizor", "canal"], as_index=False)
          ["qty"].sum()
    )
    totals = df.groupby(["furnizor", "canal"])["qty"].transform("sum")
    df["share"] = df["qty"] / totals.replace(0, pd.NA)
    df["share"] = df["share"].fillna(0)
    return df[["cod_produs", "sku", "furnizor", "canal", "share", "qty"]]


def sku_catalog(furnizor=None, db_path=DB_PATH):
    sql = """
        SELECT cod_produs, MAX(sku) AS sku, MAX(furnizor) AS furnizor,
               MIN(data_dl) AS first_seen,
               MAX(data_dl) AS last_seen,
               SUM(cantitate) AS total_qty,
               SUM(val_neta) AS total_val
        FROM tranzactii
        WHERE cod_produs IS NOT NULL
    """
    params = {}
    if furnizor:
        sql += " AND furnizor = :furnizor"
        params["furnizor"] = furnizor
    sql += " GROUP BY cod_produs"
    with _connect(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


if __name__ == "__main__":
    # Smoke test
    print("=== weekly_brand_channel(Basilur) ===")
    df = weekly_brand_channel("Basilur")
    print(df.head())
    print(f"rows: {len(df)}, series: {df['unique_id'].nunique()}")
    print(f"date range: {df['ds'].min()} -> {df['ds'].max()}")
    print()
    print("=== sku_mix_recent(Basilur, 12w) ===")
    mix = sku_mix_recent("Basilur", 12)
    print(mix.head())
    print(f"distinct SKUs: {mix['cod_produs'].nunique()}, "
          f"channel sums: {mix.groupby('canal')['share'].sum().to_dict()}")
