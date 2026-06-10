"""Torb forecasting engine.

Modules:
    schema   — SQLite DDL for forecast tables and brand config.
    data     — weekly series extraction from tranzactii.
    segment  — ADI/CV^2 classification of SKU demand patterns.
    models   — ETS / CrostonSBA / SeasonalNaive wrappers + Q4 overlay.
    hierarchy — middle-out brand->SKU allocation.
    reorder  — safety stock, reorder point, suggested order.
    backtest — rolling-origin evaluation.
    run      — end-to-end orchestration (CLI: python -m forecast.run).
    export   — Excel report generation.
"""
