# Run the forecast CLI from the project root.
# Usage: .\tools\run_forecast.ps1 [--brand Basilur] [--horizon 20] [--all]
$env:PYTHONPATH = "app;$env:PYTHONPATH"
python -m forecast.run @args
