# Shopify Sync History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent sync history panel to the Shopify stock sync page so users can browse past sync sessions and load them as read-only views into the main table.

**Architecture:** Two new SQLite tables store sync metadata and synced rows. Three new/modified API endpoints serve the history data. The HTML page gains a right-side history card, and the JS gains history table rendering, row selection, historical view mode, and auto-refresh after sync.

**Tech Stack:** Python/Flask (async blueprint), SQLite (via existing migration runner), Vanilla JS (no new dependencies), Bootstrap 5 (already used).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `migrations/0006_20260605_shopify_sync_log.py` | Create | DB schema for history tables |
| `tests/conftest.py` | Modify | Add `db_path` fixture |
| `tests/test_blueprint_stocuri_shopify.py` | Modify | Tests for 2 new GET endpoints + modified POST sync |
| `app/blueprints/stocuri_shopify.py` | Modify | 2 new GET endpoints; modify POST sync to save history |
| `app/templates/stocuri/shopify.html` | Modify | Right card + banner element + updated button row |
| `app/static/js/stocuri-shopify.js` | Modify | History table, row selection, historical view, refresh after sync |

---

## Task 1: Migration 0006 — shopify_sync_sessions + shopify_sync_rows

**Files:**
- Create: `migrations/0006_20260605_shopify_sync_log.py`

- [ ] **Step 1: Create migration file**

```python
"""Migration 0006 — Shopify sync history tables."""

VERSION = 6
NAME = "0006_20260605_shopify_sync_log"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shopify_sync_sessions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_at   TEXT    NOT NULL,
            filename  TEXT
        );

        CREATE TABLE IF NOT EXISTS shopify_sync_rows (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL,
            inventory_item_id   TEXT,
            sku                 TEXT,
            name                TEXT,
            old_stock           INTEGER,
            new_stock           INTEGER,
            status              TEXT
        );
    """)
```

- [ ] **Step 2: Apply migration and verify**

Run from project root:
```
python migrations/runner.py
```
Expected output ends with:
```
  Applying 0006: 0006_20260605_shopify_sync_log ...
  0006 OK.
```

- [ ] **Step 3: Commit**

```
git add migrations/0006_20260605_shopify_sync_log.py
git commit -m "feat: add migration 0006 for shopify sync history tables"
```

---

## Task 2: GET /api/stocuri/shopify/sync-history endpoint + tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_blueprint_stocuri_shopify.py`
- Modify: `app/blueprints/stocuri_shopify.py`

- [ ] **Step 1: Add `db_path` fixture to conftest.py**

In `tests/conftest.py`, after the `client` fixture, add:

```python
@pytest.fixture(scope='session')
def db_path():
    return _TEST_DB
```

- [ ] **Step 2: Write failing tests for GET sync-history**

In `tests/test_blueprint_stocuri_shopify.py`, add after the existing test:

```python
import sqlite3 as _sqlite3


def _seed_session(db_path, filename='test.xlsx', sync_at='2026-06-05 14:32:00'):
    """Insert one session with two rows; return session_id."""
    with _sqlite3.connect(db_path) as c:
        cur = c.execute(
            "INSERT INTO shopify_sync_sessions (sync_at, filename) VALUES (?, ?)",
            (sync_at, filename),
        )
        session_id = cur.lastrowid
        c.executemany(
            """INSERT INTO shopify_sync_rows
               (session_id, inventory_item_id, sku, name, old_stock, new_stock, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (session_id, 'IID001', 'SKU001', 'Produs A', 10, 20, 'updated'),
                (session_id, 'IID002', 'SKU002', 'Produs B', 5, 0, 'updated'),
            ],
        )
    return session_id


def test_sync_history_returns_list(client):
    resp = client.get('/api/stocuri/shopify/sync-history')
    assert resp.status_code == 200
    import json
    data = json.loads(resp.data)
    assert isinstance(data, list)


def test_sync_history_returns_seeded_session(client, db_path):
    import json
    session_id = _seed_session(db_path, filename='raport_stoc.xlsx')
    resp = client.get('/api/stocuri/shopify/sync-history')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    session = next((s for s in data if s['id'] == session_id), None)
    assert session is not None
    assert session['filename'] == 'raport_stoc.xlsx'
    assert '-' in session['sync_at']   # formatted as dd-mm-yyyy HH:MM


def test_sync_history_max_ten(client, db_path):
    import json
    for i in range(12):
        _seed_session(db_path, filename=f'batch_{i}.xlsx')
    resp = client.get('/api/stocuri/shopify/sync-history')
    data = json.loads(resp.data)
    assert len(data) <= 10
```

- [ ] **Step 3: Run tests to verify they fail**

```
python -m pytest tests/test_blueprint_stocuri_shopify.py -v -k "sync_history"
```
Expected: FAIL — `404` or `AttributeError` (endpoint doesn't exist yet).

- [ ] **Step 4: Implement the endpoint**

In `app/blueprints/stocuri_shopify.py`, add these imports at the top (after existing imports):

```python
import sqlite3
from datetime import datetime
from paths import DB_PATH
```

Then add this route after `api_shopify_connection_test`:

```python
@stocuri_shopify_bp.route('/api/stocuri/shopify/sync-history')
def api_shopify_sync_history():
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT id, sync_at, filename FROM shopify_sync_sessions"
                " ORDER BY id DESC LIMIT 10"
            ).fetchall()
        result = []
        for r in rows:
            try:
                dt = datetime.fromisoformat(r['sync_at'])
                formatted = dt.strftime('%d-%m-%Y %H:%M')
            except Exception:
                formatted = r['sync_at']
            result.append({
                'id': r['id'],
                'sync_at': formatted,
                'filename': r['filename'] or '',
            })
        return jsonify(result)
    except Exception as exc:
        logger.exception("Shopify sync history fetch failed")
        return jsonify({'error': str(exc)}), 500
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_blueprint_stocuri_shopify.py -v -k "sync_history"
```
Expected: `test_sync_history_returns_list` PASS, `test_sync_history_returns_seeded_session` PASS, `test_sync_history_max_ten` PASS.

- [ ] **Step 6: Commit**

```
git add tests/conftest.py tests/test_blueprint_stocuri_shopify.py app/blueprints/stocuri_shopify.py
git commit -m "feat: add GET /api/stocuri/shopify/sync-history endpoint"
```

---

## Task 3: GET /api/stocuri/shopify/sync-history/<session_id> endpoint + tests

**Files:**
- Modify: `tests/test_blueprint_stocuri_shopify.py`
- Modify: `app/blueprints/stocuri_shopify.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_blueprint_stocuri_shopify.py`, add:

```python
def test_sync_history_rows_for_session(client, db_path):
    import json
    session_id = _seed_session(db_path, filename='rows_test.xlsx')
    resp = client.get(f'/api/stocuri/shopify/sync-history/{session_id}')
    assert resp.status_code == 200
    rows = json.loads(resp.data)
    assert len(rows) == 2
    skus = {r['sku'] for r in rows}
    assert skus == {'SKU001', 'SKU002'}
    assert rows[0]['status'] == 'updated'


def test_sync_history_rows_unknown_session(client):
    import json
    resp = client.get('/api/stocuri/shopify/sync-history/99999')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_blueprint_stocuri_shopify.py -v -k "sync_history_rows"
```
Expected: FAIL — `404`.

- [ ] **Step 3: Implement the endpoint**

In `app/blueprints/stocuri_shopify.py`, add after `api_shopify_sync_history`:

```python
@stocuri_shopify_bp.route('/api/stocuri/shopify/sync-history/<int:session_id>')
def api_shopify_sync_history_rows(session_id):
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                """SELECT inventory_item_id, sku, name, old_stock, new_stock, status
                   FROM shopify_sync_rows WHERE session_id = ?""",
                (session_id,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        logger.exception("Shopify sync history rows fetch failed")
        return jsonify({'error': str(exc)}), 500
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_blueprint_stocuri_shopify.py -v -k "sync_history_rows"
```
Expected: both PASS.

- [ ] **Step 5: Commit**

```
git add tests/test_blueprint_stocuri_shopify.py app/blueprints/stocuri_shopify.py
git commit -m "feat: add GET /api/stocuri/shopify/sync-history/<session_id> endpoint"
```

---

## Task 4: Modify POST /api/stocuri/shopify/sync to save history

**Files:**
- Modify: `tests/test_blueprint_stocuri_shopify.py`
- Modify: `app/blueprints/stocuri_shopify.py`

- [ ] **Step 1: Write failing test**

In `tests/test_blueprint_stocuri_shopify.py`, add:

```python
def test_sync_saves_history_to_db(client, db_path):
    import json
    from unittest.mock import patch, AsyncMock

    fake_result = type('R', (), {
        'results': [
            {'ok': True,  'inventory_item_id': 'IID_HIST_A',
             'sku': 'SKU_A', 'name': 'Produs A', 'error': None},
            {'ok': False, 'inventory_item_id': 'IID_HIST_B',
             'sku': 'SKU_B', 'name': 'Produs B', 'error': 'timeout'},
        ],
        'success_count': 1,
        'error_count': 1,
    })()

    payload = {
        'report_filename': 'stoc_test.xlsx',
        'rows_to_update': [
            {'inventory_item_id': 'IID_HIST_A', 'sku': 'SKU_A',
             'name': 'Produs A', 'old_stock': 5, 'new_stock': 10},
            {'inventory_item_id': 'IID_HIST_B', 'sku': 'SKU_B',
             'name': 'Produs B', 'old_stock': 3, 'new_stock': 0},
        ],
    }

    with patch('blueprints.stocuri_shopify.sync', new=AsyncMock(return_value=fake_result)):
        resp = client.post(
            '/api/stocuri/shopify/sync',
            data=json.dumps(payload),
            content_type='application/json',
        )

    assert resp.status_code == 200

    with _sqlite3.connect(db_path) as c:
        c.row_factory = _sqlite3.Row
        session = c.execute(
            "SELECT * FROM shopify_sync_sessions WHERE filename='stoc_test.xlsx'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert session is not None

        rows = c.execute(
            "SELECT * FROM shopify_sync_rows WHERE session_id=?", (session['id'],)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]['inventory_item_id'] == 'IID_HIST_A'
        assert rows[0]['old_stock'] == 5
        assert rows[0]['new_stock'] == 10
        assert rows[0]['status'] == 'updated'
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_blueprint_stocuri_shopify.py -v -k "test_sync_saves_history"
```
Expected: FAIL — assertion error (no DB write yet).

- [ ] **Step 3: Modify api_shopify_sync**

Replace the existing `api_shopify_sync` function in `app/blueprints/stocuri_shopify.py` with:

```python
@stocuri_shopify_bp.route('/api/stocuri/shopify/sync', methods=['POST'])
async def api_shopify_sync():
    try:
        data = request.get_json(force=True)
        rows_to_update = data.get('rows_to_update', [])
        report_filename = data.get('report_filename', '')
        result = await sync(rows_to_update)

        successful_ids = {
            r['inventory_item_id'] for r in result.results if r.get('ok')
        }
        rows_by_id = {r['inventory_item_id']: r for r in rows_to_update}
        rows_to_save = [rows_by_id[iid] for iid in successful_ids if iid in rows_by_id]

        if rows_to_save:
            with sqlite3.connect(DB_PATH) as c:
                cur = c.execute(
                    "INSERT INTO shopify_sync_sessions (sync_at, filename)"
                    " VALUES (datetime('now','localtime'), ?)",
                    (report_filename,),
                )
                session_id = cur.lastrowid
                c.executemany(
                    """INSERT INTO shopify_sync_rows
                       (session_id, inventory_item_id, sku, name, old_stock, new_stock, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'updated')""",
                    [
                        (session_id, r['inventory_item_id'], r.get('sku', ''),
                         r.get('name', ''), r.get('old_stock'), r['new_stock'])
                        for r in rows_to_save
                    ],
                )

        return jsonify({
            'results': result.results,
            'success_count': result.success_count,
            'error_count': result.error_count,
        })
    except Exception as exc:
        logger.exception("Shopify sync failed")
        return jsonify({'error': str(exc)}), 500
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_blueprint_stocuri_shopify.py -v -k "test_sync_saves_history"
```
Expected: PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```
python -m pytest tests/ -v
```
Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```
git add tests/test_blueprint_stocuri_shopify.py app/blueprints/stocuri_shopify.py
git commit -m "feat: save sync history to DB on successful Sincronizeaza pe Shopify"
```

---

## Task 5: HTML — right card, banner, button row

**Files:**
- Modify: `app/templates/stocuri/shopify.html`

- [ ] **Step 1: Replace the card + button block**

Replace the entire `<div class="mb-3">` card section and `<div class="d-flex gap-2 mb-3">` button row in `shopify.html` with the following:

```html
<div class="d-flex gap-3 mb-3 flex-wrap align-items-start">
  <!-- Left card: unchanged -->
  <div class="dz-card p-3 border rounded" style="min-width:320px; max-width:480px;">
    <div class="fw-semibold mb-1">Raport intern stocuri</div>
    <div class="text-secondary small mb-2">.xls / .xlsx — match dupa coloana <code>codmare</code></div>
    <div class="dropzone" id="dzShopReport">
      <input type="file" id="fileShopReport" accept=".xls,.xlsx" hidden />
      <div class="dz-inner text-center py-3">
        <strong>Trage fisierul aici</strong><br>
        <span class="text-secondary small">sau click pentru a alege</span><br>
        <small id="nameShopReport" class="text-info"></small>
      </div>
    </div>
  </div>

  <!-- Right card: Istoric sincronizari -->
  <div class="dz-card p-3 border rounded" style="min-width:320px; max-width:480px;">
    <div class="fw-semibold mb-1">Istoric sincronizari</div>
    <div class="table-responsive" style="max-height:180px; overflow-y:auto;">
      <table class="table table-sm table-hover mb-0" id="syncHistoryTable">
        <thead>
          <tr>
            <th>Data</th>
            <th>Fisier</th>
          </tr>
        </thead>
        <tbody id="syncHistoryBody"></tbody>
      </table>
    </div>
  </div>
</div>

<div class="d-flex gap-2 mb-3">
  <button id="btnShopPreview" class="btn btn-primary">Incarca stoc Shopify</button>
  <button id="btnHistoryLoad" class="btn btn-secondary" disabled>Incarca date</button>
  <button id="btnShopSync" class="btn btn-success" disabled>Sincronizeaza pe Shopify</button>
</div>

<div id="shopHistoricalBanner" class="alert alert-info py-2 px-3 mb-2" hidden>
  <small id="shopHistoricalBannerText"></small>
</div>
```

- [ ] **Step 2: Verify page loads without JS errors**

Start the dev server (`Start-Hub.bat` or `tools\Start-Hub.ps1`) and open `http://localhost:5000/stocuri/shopify` (or whatever the URL is per the existing route). Confirm the two cards appear side by side, the history table renders (even if empty), and no console errors appear.

- [ ] **Step 3: Commit**

```
git add app/templates/stocuri/shopify.html
git commit -m "feat: add Istoric sincronizari card and updated button row to Shopify page"
```

---

## Task 6: JS — history table, selection, historical view, refresh after sync

**Files:**
- Modify: `app/static/js/stocuri-shopify.js`

- [ ] **Step 1: Add new DOM refs and state variables**

At the top of `stocuri-shopify.js`, after the existing `const` declarations (around line 93), add:

```javascript
const btnHistoryLoad        = document.getElementById("btnHistoryLoad");
const syncHistoryBody       = document.getElementById("syncHistoryBody");
const shopHistoricalBanner  = document.getElementById("shopHistoricalBanner");
const shopHistoricalBannerText = document.getElementById("shopHistoricalBannerText");

let selectedHistorySessionId = null;
let isHistoricalView = false;
```

- [ ] **Step 2: Add history table render and load functions**

After the new DOM refs, add:

```javascript
// ───────────── Sync history ─────────────
function renderSyncHistory(sessions) {
  if (!sessions || !sessions.length) {
    syncHistoryBody.innerHTML =
      '<tr><td colspan="2" class="text-secondary small">Niciun istoric disponibil</td></tr>';
    return;
  }
  syncHistoryBody.innerHTML = sessions
    .map(
      (s) =>
        `<tr class="sync-history-row" data-session-id="${s.id}" style="cursor:pointer;">
           <td class="small text-nowrap">${escapeHtml(s.sync_at)}</td>
           <td class="small text-truncate" style="max-width:200px;" title="${escapeHtml(s.filename)}">${escapeHtml(s.filename)}</td>
         </tr>`
    )
    .join("");
}

async function loadSyncHistory() {
  try {
    const resp = await fetch("/api/stocuri/shopify/sync-history");
    const sessions = await resp.json();
    renderSyncHistory(sessions);
  } catch (e) {
    syncHistoryBody.innerHTML =
      '<tr><td colspan="2" class="text-secondary small">Eroare la incarcare.</td></tr>';
  }
}

loadSyncHistory();
```

- [ ] **Step 3: Add history row selection handler**

After `loadSyncHistory()`, add:

```javascript
syncHistoryBody.addEventListener("click", (e) => {
  const row = e.target.closest(".sync-history-row");
  if (!row) return;
  syncHistoryBody
    .querySelectorAll(".sync-history-row")
    .forEach((r) => r.classList.remove("table-active"));
  row.classList.add("table-active");
  selectedHistorySessionId = parseInt(row.dataset.sessionId, 10);
  btnHistoryLoad.disabled = false;
});
```

- [ ] **Step 4: Add historical view render function and exit helper**

```javascript
function renderHistoricalView(rows, syncAt) {
  isHistoricalView = true;

  shopTableBody.innerHTML = rows
    .map((r) => renderShopRow(r, null))
    .join("");
  shopTableBody
    .querySelectorAll("input[type=checkbox]")
    .forEach((cb) => { cb.disabled = true; });
  shopSelectAll.disabled = true;

  shopHistoricalBannerText.textContent = `Vizualizare istorica — ${syncAt}`;
  shopHistoricalBanner.hidden = false;

  shopSummaryEl.innerHTML = "";
  shopIssuesEl.innerHTML = "";
  shopToolbarEl.hidden = true;
  shopPaginationInfo.textContent = `${rows.length} produse sincronizate`;
  shopPrevPageBtn.disabled = true;
  shopNextPageBtn.disabled = true;
  btnShopSync.disabled = true;

  shopPreviewSection.hidden = false;
  shopSyncResults.hidden = true;
}

function exitHistoricalView() {
  if (!isHistoricalView) return;
  isHistoricalView = false;
  shopHistoricalBanner.hidden = true;
  shopSelectAll.disabled = false;
}
```

- [ ] **Step 5: Add "Incarca date" click handler**

```javascript
btnHistoryLoad.addEventListener("click", async () => {
  if (!selectedHistorySessionId) return;
  btnHistoryLoad.disabled = true;
  btnHistoryLoad.innerHTML =
    '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se incarca...';
  try {
    const resp = await fetch(
      `/api/stocuri/shopify/sync-history/${selectedHistorySessionId}`
    );
    const rows = await resp.json();
    const activeRow = syncHistoryBody.querySelector(".sync-history-row.table-active");
    const syncAt = activeRow ? activeRow.cells[0].textContent : "";
    renderHistoricalView(rows, syncAt);
  } catch (e) {
    setShopStatus("Eroare la incarcarea datelor istorice: " + e.message, "error");
  } finally {
    btnHistoryLoad.disabled = false;
    btnHistoryLoad.textContent = "Incarca date";
  }
});
```

- [ ] **Step 6: Modify runShopPreview to exit historical mode**

In the existing `runShopPreview` function, add `exitHistoricalView();` as the very first line of the function body:

```javascript
async function runShopPreview() {
  exitHistoricalView();          // ← add this line
  setShopStatus("", "");
  // ... rest unchanged ...
```

- [ ] **Step 7: Modify runShopSync to send old_stock + filename and refresh history**

In `runShopSync`, replace the `rows_to_update` construction and the `fetch` call:

**Replace this block:**
```javascript
  const rows_to_update = changed.map((r) => ({
    inventory_item_id: r.inventory_item_id,
    sku:       r.sku || "",
    name:      r.name,
    new_stock: r.new_stock,
  }));
```

**With:**
```javascript
  const rows_to_update = changed.map((r) => ({
    inventory_item_id: r.inventory_item_id,
    sku:       r.sku || "",
    name:      r.name,
    old_stock: r.old_stock ?? null,
    new_stock: r.new_stock,
  }));
  const report_filename = shopReportFile ? shopReportFile.name : "";
```

**Replace the fetch call:**
```javascript
    const resp = await fetch("/api/stocuri/shopify/sync", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows_to_update }),
    });
```

**With:**
```javascript
    const resp = await fetch("/api/stocuri/shopify/sync", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows_to_update, report_filename }),
    });
```

Then after the `renderSyncResults(data);` call inside the `try` block, add:
```javascript
    await loadSyncHistory();
```

- [ ] **Step 8: Verify the full flow manually**

Start the app and exercise the golden path:
1. Upload a report file → "Incarca stoc Shopify" → table loads with diffs.
2. Select some items → "Sincronizeaza pe Shopify" → sync completes → history table updates with new row.
3. Click the new history row → "Incarca date" → table shows historical rows, checkboxes disabled, banner visible, "Sincronizeaza pe Shopify" disabled.
4. Click "Incarca stoc Shopify" → historical banner disappears, table reloads in live mode.

- [ ] **Step 9: Commit**

```
git add app/static/js/stocuri-shopify.js
git commit -m "feat: add sync history panel, Incarca date, and historical view mode"
```
