# Torb Logistic — Project Context

AI consulting for **Torb Logistic SRL**, a Romanian FMCG distributor. Goal: identify and implement AI/agentic automation to optimize business operations. This is a Flask + SQLite app.

## Working preferences
- **English** for all developer communication (code, comments, commit messages, responses); **Romanian** for UI text, user-facing strings, and end-user manuals.
- Keep token usage minimal: concise code, no over-commenting, short responses, no "here's what I changed" summaries unless asked.
- Before any batch operation (multi-file edits, bulk scripts), save progress to memory first so work can resume after a context reset.

## Code quality rules (enforced in CI)
- **Linter**: `ruff` — all Python must pass `ruff check .` with zero errors before commit.
- **Auto-fix hook**: a `PostToolUse` hook in `~/.claude/settings.json` runs `ruff check --fix --quiet` on every `.py` file Claude writes or edits. No manual lint pass needed.
- **Forbidden patterns**: `E401` (multiple imports), `E402` (import not at top), `E701/E702` (compound statements), `E722` (bare except), `E741` (ambiguous names `l`, `O`, `I`), `F401` (unused imports), `F841` (unused variables).

## Read-on-demand routing
CLAUDE.md is injected every turn, so it holds only routing + file-placement rules. **Read nothing else until the task calls for it**, then read the matching file(s):

| Working on... | Read first |
|---------------|-----------|
| strategy / roadmap / company / risks | `docs/BUSINESS.md` — key facts at the top; §7 = the 2026–2030 plan. Don't reinterpret strategy from scratch; start here. |
| current state / next step / open decisions | `context/STATUS.md` — in progress / blocked / next step + open strategic decisions & 90-day actions. **Update on every state change.** Delivery summaries live in `CHANGELOG.md`, not here. |
| what shipped / delivery history / a past change | `CHANGELOG.md` — dated summary of every delivered change (Keep-a-Changelog; `[Unreleased]` accrues until a release). The canonical home for implementation summaries. |
| domain terms / data model / bonus / virtual brands / stock sync | `docs/BUSINESS_LOGIC.md` |
| data / SQLite / ETL / Excel / data-file map | `docs/TECHNICAL.md` §Data |
| forecast / backtest / reorder | `app/forecast/README.md` |
| deploy / VPS / secrets | `docs/TECHNICAL.md` |
| Romanian strings in `.py` files | `docs/TECHNICAL.md` §Encoding — **critical, read before editing any `.py` with Romanian text** |
| Typst user manuals (`docs/manuals/`) | `docs/TECHNICAL.md` §Typst |
| frontend error display / any user-facing error handler | `docs/TECHNICAL.md` §Frontend conventions — **always** surface errors via the shared `AppError.show()` modal (`app/static/js/app-error.js`), never ad-hoc inline text. |
| tech-debt / open issues backlog | `docs/BACKLOG.md` |

`docs/TECHNICAL_history.md` is a write-mostly archive; read only when investigating a past change.

Actual open priorities: see "Next immediate step" in `context/STATUS.md`.

## Project Directory Structure

All new files must follow this layout. Never add `.py` files to root.

| Directory | What goes here |
|-----------|---------------|
| `app/` | Flask web application only: routes, db, queries, AI helpers, Excel/PPT exports, migrations |
| `etl/` | Data pipeline scripts: `import_*.py`, `rebuild_*.py`, `init_*.py`, `update_*.py` |
| `app/forecast/` | Forecast package: statistical engine, data queries, CLI, Flask-facing logic, AI agent |
| `tools/` | Windows launcher scripts (`Start-Hub.ps1`); `Start-Hub.bat` is at project root |
| `tests/` | pytest test files |
| `context/` | Live execution tracker only (`STATUS.md`) |
| `docs/` | Consolidated docs (`BUSINESS.md`, `BUSINESS_LOGIC.md`, `TECHNICAL.md`, `BACKLOG.md`), analysis docs (`analysis/`), implementation plans (`plans/`), design specs (`specs/`, gitignored), user manuals (`manuals/`) |
| `docs_input/` | Input Excel/CSV data files (never committed, gitignored) |
| `data/` | SQLite database and generated outputs (gitignored) |
| Root | Config/doc files only: `requirements.txt`, `.gitignore`, `.env.example`, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `Start-Hub.bat` |

### Rules when creating new files
- New Flask route or feature module → `app/`
- New import from Excel/ERP/supplier file → `etl/`
- New Windows launcher script → `tools/`
- New forecast model, backtest, or forecast CLI tool → `app/forecast/`
- New pytest test → `tests/`
- Superpowers/AI-workflow outputs go **directly under `docs/`** — never create a `docs/superpowers/` directory: design specs → `docs/specs/YYYY-MM-DD-<topic>-design.md`, implementation plans → `docs/plans/`, analysis docs → `docs/analysis/`
- Compiled user-manual PDFs → `docs/manuals/manual_<name>.pdf` (Typst sources stay in `docs/manuals/<name>/`, gitignored)
- **Adding a nav menu link** → register it in `app/nav_registry.py` (`NAV_REGISTRY`) with its `endpoints`/`blueprint`; never add a raw `<a>` nav link to `base.html`. Registration auto-lists it in **Admin → Autorizări** and turns on its `403` route enforcement. New links are deny-by-default until granted in the matrix. `tests/test_endpoint_coverage.py` fails if a new business endpoint is left un-gated and un-allowlisted.

### Import path note for etl/ scripts
ETL scripts use CWD-relative paths (`"data/torb.db"`, `"docs_input/..."`). Always run them from the project root:
```
python etl/import_preturi.py
```
If a script needs to import sibling modules from `etl/`, add at the top:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```
