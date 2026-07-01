# Torb Logistic — Project Context

AI consulting for **Torb Logistic SRL**, a Romanian FMCG distributor. Goal: identify and implement AI/agentic automation to optimize business operations. This is a Flask + SQLite app.

## Code quality rules (enforced in CI)
- **Linter**: `ruff` — all Python must pass `ruff check .` with zero errors before commit.
- **Auto-fix hook**: a `PostToolUse` hook in `~/.claude/settings.json` runs `ruff check --fix --quiet` on every `.py` file Claude writes or edits. No manual lint pass needed.
- **Forbidden patterns**: `E401` (multiple imports), `E402` (import not at top), `E701/E702` (compound statements), `E722` (bare except), `E741` (ambiguous names `l`, `O`, `I`), `F401` (unused imports), `F841` (unused variables).

## Read-on-demand routing
CLAUDE.md is injected every turn, so it holds only routing + file-placement rules. **Read nothing else until the task calls for it**, then read the matching file(s):

| Working on... | Read first |
|---------------|-----------|
| strategy / roadmap | `context/plan_strategic_5ani.md` — the 2026–2030 plan. Don't reinterpret strategy from scratch; start here. |
| current state / next step | `context/STATUS.md` — what's delivered / in progress / blocked. **Update it on every state change.** |
| business facts, brands, data-file map | `context/key_facts.md` |
| data / SQLite / ETL / Excel | `.claude/project_knowledge.md` §Data |
| forecast / backtest / reorder | `app/forecast/README.md` |
| deploy / VPS / secrets / Shopify sync | `.claude/project_knowledge.md` |
| Romanian strings in `.py` files | `.claude/project_knowledge.md` §Encoding — **critical, read before editing any `.py` with Romanian text** |
| Typst user manuals (`docs/manuals/`) | `.claude/project_knowledge.md` §Typst |
| tech-debt backlog | `.claude/project_knowledge.md` §Tech-debt |

Other `context/*.md` are research findings — read when relevant. **Exception:** `*_history.md` files are write-mostly archives; read only when investigating a past change.

Actual #1 open question: bonusarea automată lunară (pasul 5 din `context/STATUS.md`, deadline depășit) + validarea forecast Basilur cu owner-ul.

## Project Directory Structure

All new files must follow this layout. Never add `.py` files to root.

| Directory | What goes here |
|-----------|---------------|
| `app/` | Flask web application only: routes, db, queries, AI helpers, Excel/PPT exports, migrations |
| `etl/` | Data pipeline scripts: `import_*.py`, `rebuild_*.py`, `init_*.py`, `update_*.py` |
| `app/forecast/` | Forecast package: statistical engine, data queries, CLI, Flask-facing logic, AI agent |
| `tools/` | Windows launcher scripts (`Start-Hub.ps1`); `Start-Hub.bat` is at project root |
| `tests/` | pytest test files |
| `context/` | Project research, reference markdown, strategic docs (`plan_strategic_5ani.md`, `STATUS.md`, `key_facts.md`) |
| `docs/` | Implementation plans (`plans/`), analysis docs (`analysis/`), AI-generated specs (`superpowers/`), user manuals (`manuals/`) |
| `docs_input/` | Input Excel/CSV data files (never committed, gitignored) |
| `data/` | SQLite database and generated outputs (gitignored) |
| Root | Config/doc files only: `requirements.txt`, `.gitignore`, `.env.example`, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `Start-Hub.bat` |

### Rules when creating new files
- New Flask route or feature module → `app/`
- New import from Excel/ERP/supplier file → `etl/`
- New Windows launcher script → `tools/`
- New forecast model, backtest, or forecast CLI tool → `app/forecast/`
- New pytest test → `tests/`

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
