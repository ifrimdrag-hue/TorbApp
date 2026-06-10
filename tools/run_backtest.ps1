# Run the forecast backtest CLI from the project root.
# Usage: .\tools\run_backtest.ps1 [--brand Basilur] [--all]
$env:PYTHONPATH = "app;$env:PYTHONPATH"
python -m forecast.backtest @args
