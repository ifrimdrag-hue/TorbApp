// ───────────── Helpers ─────────────
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function issueBlock(kind, title, items) {
  const list = items.slice(0, 200).map((x) => `<li>${escapeHtml(String(x))}</li>`).join("");
  const more = items.length > 200 ? `<div class="text-secondary mt-1">… si inca ${items.length - 200}</div>` : "";
  return `<div class="issue-block mb-2">
    <div class="issue-head ${kind} d-flex justify-content-between align-items-center p-2 rounded" style="cursor:pointer;">
      <span>${escapeHtml(title)}</span><span class="badge bg-secondary">${items.length}</span>
    </div>
    <div class="issue-body p-2" hidden><ul class="mb-0">${list}</ul>${more}</div>
  </div>`;
}

function bindIssueHeads(el) {
  el.querySelectorAll(".issue-head").forEach((h) =>
    h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; })
  );
}

// ───────────── Platform configs ─────────────
const STATUS_LABELS = {
  updated:          '<span class="badge bg-success">Actualizat</span>',
  zeroed_threshold: '<span class="badge bg-warning text-dark">Zerificate (stoc mic)</span>',
  unchanged:        '<span class="badge bg-secondary">Nemodificat</span>',
  no_report:        '<span class="badge bg-secondary">–</span>',
  no_ean:           '<span class="badge bg-secondary">Fara EAN</span>',
  no_sku:           '<span class="badge bg-secondary">Fara SKU</span>',
};

const PLATFORMS = {
  emag: {
    previewUrl: "/api/stocuri/emag/preview",
    syncUrl:    "/api/stocuri/emag/sync",
    connUrl:    "/api/stocuri/emag/connection-test",
    desc:       "Incarca raportul intern de stocuri. Aplicatia preia ofertele live din eMAG si iti arata diferentele. Bifezi ce vrei sa actualizezi si apesi Sincronizeaza.",
    idField:    "offer_id",
    skuField:   "ean",
    skuLabel:   "EAN",
    noSkuStatus:"no_ean",
    noSkuFilter:"Fara EAN",
    hasExtra:   true,
    stockLabel: "Stoc eMAG",
    previewBtn: "Incarca stoc eMAG",
    syncBtn:    "Sincronizeaza pe eMAG",
    historyUrl:     "/api/stocuri/emag/sync-history",
    historyRowsUrl: (id) => `/api/stocuri/emag/sync-history/${id}`,
    buildPayload(rows, filename = "") {
      return {
        rows_to_update: rows.map((r) => ({
          offer_id: r.offer_id, ean: r.ean || "", name: r.name,
          old_stock: r.old_stock ?? null, new_stock: r.new_stock,
          part_number_key: r.part_number_key || "",
        })),
        report_filename: filename,
      };
    },
    renderSummary(s) {
      return `
        <div class="stat"><div class="label">Total oferte eMAG</div><div class="value">${s.total_emag_offers}</div></div>
        <div class="stat success"><div class="label">De actualizat</div><div class="value">${s.updated_with_stock}</div></div>
        <div class="stat warning"><div class="label">Zerificate (&le;${s.safety_threshold})</div><div class="value">${s.zeroed_threshold}</div></div>
        <div class="stat muted"><div class="label">Nemodificate</div><div class="value">${s.unchanged}</div></div>
        <div class="stat muted"><div class="label">Fara EAN</div><div class="value">${s.no_ean}</div></div>
        <div class="stat muted"><div class="label">Negasite pe eMAG</div><div class="value">${s.not_in_emag}</div></div>`;
    },
    renderSummaryNoReport(s) {
      return `${s.total_emag_offers} oferte preluate din eMAG` +
        (s.no_ean > 0 ? ` &middot; <span class="emag-summary-warn">${s.no_ean} fara EAN</span>` : "");
    },
    renderIssues(data) {
      const blocks = [];
      if (data.warnings?.length) blocks.push(issueBlock("warning", "Avertismente parsare raport", data.warnings));
      if (data.skus_not_in_emag?.length)
        blocks.push(issueBlock("warning", "SKU-uri din raport negasite pe eMAG",
          data.skus_not_in_emag.map((r) => `SKU ${r.sku} — EAN ${r.ean} — qty ${r.qty}`)));
      return blocks;
    },
    renderRow(r, selectedIds) {
      const id = String(r.offer_id);
      const can = r.status === "updated" || r.status === "zeroed_threshold";
      const checked = selectedIds.has(id);
      const newCell = r.new_stock != null ? r.new_stock : '<span class="text-secondary">–</span>';
      return `<tr class="emag-row emag-row--${r.status}">
        <td><input type="checkbox" class="stoc-row-check" data-id="${id}"
             ${can ? (checked ? "checked" : "") : "disabled"} /></td>
        <td class="emag-name">${escapeHtml(r.name)}</td>
        <td><code>${escapeHtml(r.ean || "—")}</code></td>
        <td><code>${escapeHtml(r.part_number_key || "—")}</code></td>
        <td style="text-align:right;">${r.old_stock}</td>
        <td style="text-align:right;">${newCell}</td>
        <td>${STATUS_LABELS[r.status] || escapeHtml(r.status)}</td>
      </tr>`;
    },
    rowId: (r) => String(r.offer_id),
    previewMsg: (s) => `Gata. ${s.to_update} oferte vor fi actualizate.`,
    syncErrorLabel: (r) => `${r.name} (EAN ${r.ean || "—"}): ${r.error}`,
  },

  shopify: {
    previewUrl: "/api/stocuri/shopify/preview",
    syncUrl:    "/api/stocuri/shopify/sync",
    connUrl:    "/api/stocuri/shopify/connection-test",
    desc:       "Incarca raportul intern de stocuri. Aplicatia preia inventarul live din Shopify si iti arata diferentele. Bifezi ce vrei sa actualizezi si apesi Sincronizeaza.",
    idField:    "inventory_item_id",
    skuField:   "sku",
    skuLabel:   "SKU",
    noSkuStatus:"no_sku",
    noSkuFilter:"Fara SKU",
    hasExtra:   false,
    stockLabel: "Stoc Shopify",
    previewBtn:     "Incarca stoc Shopify",
    syncBtn:        "Sincronizeaza pe Shopify",
    historyUrl:     "/api/stocuri/shopify/sync-history",
    historyRowsUrl: (id) => `/api/stocuri/shopify/sync-history/${id}`,
    buildPayload(rows, filename = "") {
      return {
        rows_to_update: rows.map((r) => ({
          inventory_item_id: r.inventory_item_id,
          sku: r.sku || "",
          name: r.name,
          old_stock: r.old_stock ?? null,
          new_stock: r.new_stock,
        })),
        report_filename: filename,
      };
    },
    renderSummary(s) {
      return `
        <div class="stat"><div class="label">Total Shopify</div><div class="value">${s.total_shopify_items}</div></div>
        <div class="stat success"><div class="label">De actualizat</div><div class="value">${s.updated_with_stock}</div></div>
        <div class="stat warning"><div class="label">Zerificate (&le;${s.safety_threshold})</div><div class="value">${s.zeroed_threshold}</div></div>
        <div class="stat muted"><div class="label">Nemodificate</div><div class="value">${s.unchanged}</div></div>
        <div class="stat muted"><div class="label">Fara SKU</div><div class="value">${s.no_sku}</div></div>
        <div class="stat muted"><div class="label">Negasite pe Shopify</div><div class="value">${s.not_in_shopify}</div></div>`;
    },
    renderSummaryNoReport(s) {
      return `${s.total_shopify_items} produse preluate din Shopify` +
        (s.no_sku > 0 ? ` &middot; <span class="emag-summary-warn">${s.no_sku} fara SKU</span>` : "");
    },
    renderIssues(data) {
      const blocks = [];
      if (data.warnings?.length) blocks.push(issueBlock("warning", "Avertismente parsare raport", data.warnings));
      if (data.skus_not_in_shopify?.length)
        blocks.push(issueBlock("warning", "SKU-uri din raport negasite pe Shopify",
          data.skus_not_in_shopify.map((r) => `codmare ${r.codmare} — qty ${r.qty}`)));
      return blocks;
    },
    renderRow(r, selectedIds) {
      const id = r.inventory_item_id;
      const can = r.status === "updated" || r.status === "zeroed_threshold";
      const checked = selectedIds.has(id);
      const newCell = r.new_stock != null ? r.new_stock : '<span class="text-secondary">–</span>';
      return `<tr class="emag-row emag-row--${r.status}">
        <td><input type="checkbox" class="stoc-row-check" data-id="${escapeHtml(id)}"
             ${can ? (checked ? "checked" : "") : "disabled"} /></td>
        <td class="emag-name">${escapeHtml(r.name)}</td>
        <td><code>${escapeHtml(r.sku || "—")}</code></td>
        <td style="text-align:right;">${r.old_stock}</td>
        <td style="text-align:right;">${newCell}</td>
        <td>${STATUS_LABELS[r.status] || escapeHtml(r.status)}</td>
      </tr>`;
    },
    rowId: (r) => r.inventory_item_id,
    previewMsg: (s) => `Gata. ${s.to_update} produse vor fi actualizate.`,
    syncErrorLabel: (r) => `${r.name} (SKU ${r.sku || "—"}): ${r.error}`,
  },
};

// ───────────── State ─────────────
let currentPlatform = "emag";
let p = PLATFORMS.emag;
let reportFile   = null;
let previewData  = null;
let connTimer    = null;
const CONN_INTERVAL = 3 * 60 * 1000;

let selectedHistorySessionId = null;
let isHistoricalView = false;

// ───────────── DOM refs ─────────────
const connDot        = document.getElementById("connDot");
const pageDesc       = document.getElementById("pageDesc");
const btnPreview     = document.getElementById("btnPreview");
const btnSync        = document.getElementById("btnSync");
const stocStatusEl   = document.getElementById("stocStatus");
const previewSection = document.getElementById("previewSection");
const stocSummaryEl  = document.getElementById("stocSummary");
const stocIssuesEl   = document.getElementById("stocIssues");
const stocTableBody  = document.getElementById("stocTableBody");
const syncResults    = document.getElementById("syncResults");
const syncSummaryEl  = document.getElementById("syncSummary");
const syncErrorsEl   = document.getElementById("syncErrors");
const stocSelectAll  = document.getElementById("stocSelectAll");
const stocToolbarEl      = document.getElementById("stocToolbar");
const stocStatusFilterEl = document.getElementById("stocStatusFilter");
const stocFilterEl       = document.getElementById("stocFilter");
const stocSearchEl   = document.getElementById("stocSearch");
const btnStocSearch  = document.getElementById("btnStocSearch");
const stocPageInfo   = document.getElementById("stocPageInfo");
const stocPrevBtn    = document.getElementById("stocPrevPage");
const stocNextBtn    = document.getElementById("stocNextPage");
const thSku          = document.getElementById("thSku");
const thExtra        = document.getElementById("thExtra");
const thOldStock     = document.getElementById("thOldStock");
const optNoSku       = document.getElementById("optNoSku");

const shopHistoryCard          = document.getElementById("shopHistoryCard");
const btnHistoryLoad           = document.getElementById("btnHistoryLoad");
const syncHistoryBody          = document.getElementById("syncHistoryBody");
const shopHistoricalBanner     = document.getElementById("shopHistoricalBanner");
const shopHistoricalBannerText = document.getElementById("shopHistoricalBannerText");

// ───────────── Sync history (Shopify only) ─────────────
function renderSyncHistory(sessions) {
  if (!sessions || !sessions.length) {
    syncHistoryBody.innerHTML =
      '<tr><td colspan="3" class="text-secondary small">Niciun istoric disponibil</td></tr>';
    return;
  }
  syncHistoryBody.innerHTML = sessions
    .map(
      (s) =>
        `<tr class="sync-history-row" data-session-id="${s.id}" style="cursor:pointer;">
           <td class="small text-nowrap">${escapeHtml(s.sync_at)}</td>
           <td class="small text-truncate" style="max-width:200px;" title="${escapeHtml(s.filename)}">${escapeHtml(s.filename)}</td>
           <td class="small text-nowrap">${s.username ? escapeHtml(s.username) : "&mdash;"}</td>
         </tr>`
    )
    .join("");
}

async function loadSyncHistory() {
  try {
    const resp = await fetch(p.historyUrl);
    if (!resp.ok) throw new Error(resp.statusText);
    const sessions = await resp.json();
    renderSyncHistory(sessions);
  } catch (e) {
    syncHistoryBody.innerHTML =
      '<tr><td colspan="3" class="text-secondary small">Eroare la incarcare.</td></tr>';
  }
}

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

// Partial reset — caller must follow with renderPreview to restore toolbar/pagination/sync button.
function exitHistoricalView() {
  if (!isHistoricalView) return;
  isHistoricalView = false;
  shopHistoricalBanner.hidden = true;
  stocSelectAll.disabled = false;
}

function renderHistoricalView(rows, syncAt) {
  isHistoricalView = true;
  stocTableBody.innerHTML = rows.map((r) => p.renderRow(r, new Set())).join("");
  stocTableBody
    .querySelectorAll("input[type=checkbox]")
    .forEach((cb) => { cb.disabled = true; });
  stocSelectAll.disabled = true;
  shopHistoricalBannerText.textContent = `Vizualizare istorica — ${syncAt}`;
  shopHistoricalBanner.hidden = false;
  stocSummaryEl.innerHTML = "";
  stocIssuesEl.innerHTML = "";
  stocStatusFilterEl.hidden = true;
  stocPageInfo.textContent = `${rows.length} produse sincronizate`;
  stocPrevBtn.disabled = true;
  stocNextBtn.disabled = true;
  btnSync.disabled = true;
  previewSection.hidden = false;
  syncResults.hidden = true;
}

btnHistoryLoad.addEventListener("click", async () => {
  if (!selectedHistorySessionId) return;
  btnHistoryLoad.disabled = true;
  btnHistoryLoad.innerHTML =
    '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se incarca...';
  try {
    const resp = await fetch(p.historyRowsUrl(selectedHistorySessionId));
    const rows = await resp.json();
    const activeRow = syncHistoryBody.querySelector(".sync-history-row.table-active");
    const syncAt = activeRow ? activeRow.cells[0].textContent : "";
    renderHistoricalView(rows, syncAt);
  } catch (e) {
    setStatus("Eroare la incarcarea datelor istorice: " + e.message, "error");
  } finally {
    btnHistoryLoad.disabled = false;
    btnHistoryLoad.textContent = "Incarca date istorice";
  }
});

// ───────────── PaginationController ─────────────
class PaginationController {
  constructor({ pageSize, tableBody, infoEl, prevEl, nextEl }) {
    this._all = []; this._filtered = []; this._selectedIds = new Set();
    this._page = 0; this._pageSize = pageSize;
    this._tableBody = tableBody; this._infoEl = infoEl;
    this._prevEl = prevEl; this._nextEl = nextEl;
    this._sortKey = null; this._sortDir = "asc";
    this._statusFilter = ""; this._searchQuery = "";
    prevEl.addEventListener("click", () => this._goTo(this._page - 1));
    nextEl.addEventListener("click", () => this._goTo(this._page + 1));
    tableBody.addEventListener("change", (e) => {
      const cb = e.target.closest(".stoc-row-check");
      if (!cb) return;
      if (cb.checked) this._selectedIds.add(cb.dataset.id);
      else            this._selectedIds.delete(cb.dataset.id);
    });
  }
  reset() { this._all = []; this._filtered = []; this._selectedIds = new Set(); this._page = 0; this._statusFilter = ""; this._searchQuery = ""; this._tableBody.innerHTML = ""; this._infoEl.textContent = ""; this._prevEl.disabled = true; this._nextEl.disabled = true; }
  setRows(rows) {
    this._all = rows;
    this._filtered = [...rows];
    this._selectedIds = new Set(
      rows.filter((r) => r.new_stock != null && r.new_stock !== r.old_stock).map((r) => p.rowId(r))
    );
    this._applySort(); this._goTo(0);
  }
  setFilter(status) { this._statusFilter = status; this._applyFilters(); }
  setSearch(query)  { this._searchQuery  = query;  this._applyFilters(); }
  _applyFilters() {
    let rows = this._all;
    if (this._statusFilter === "updated") {
      rows = rows.filter((r) => r.new_stock != null && r.new_stock !== r.old_stock);
    } else if (this._statusFilter) {
      rows = rows.filter((r) => r.status === this._statusFilter);
    }
    if (this._searchQuery.length >= 3) {
      const q = this._searchQuery.toLowerCase();
      rows = rows.filter((r) => (r.name || "").toLowerCase().includes(q) || (r[p.skuField] || "").toLowerCase().includes(q));
    }
    this._filtered = rows;
    this._applySort(); this._goTo(0);
  }
  setSort(key) {
    this._sortDir = this._sortKey === key && this._sortDir === "asc" ? "desc" : "asc";
    this._sortKey = key; this._applySort(); this._goTo(0);
  }
  getSortState() { return { key: this._sortKey, dir: this._sortDir }; }
  _applySort() {
    if (!this._sortKey) return;
    const key = this._sortKey, dir = this._sortDir === "asc" ? 1 : -1;
    this._filtered = [...this._filtered].sort((a, b) => {
      let av = a[key], bv = b[key];
      if (av == null) return 1; if (bv == null) return -1;
      return (typeof av === "string" ? av.localeCompare(bv, "ro") : av - bv) * dir;
    });
  }
  selectAll(checked) {
    this._filtered.forEach((r) => {
      const can = r.status === "updated" || r.status === "zeroed_threshold";
      if (!can) return;
      const id = p.rowId(r);
      if (checked) this._selectedIds.add(id); else this._selectedIds.delete(id);
    });
    this._renderPage();
  }
  getSelectedRows() { return this._filtered.filter((r) => this._selectedIds.has(p.rowId(r))); }
  _goTo(page) {
    const total = this._filtered.length;
    this._page = Math.max(0, Math.min(page, Math.max(0, Math.ceil(total / this._pageSize) - 1)));
    this._renderPage();
  }
  _renderPage() {
    const total = this._filtered.length, start = this._page * this._pageSize, end = start + this._pageSize;
    this._tableBody.innerHTML = this._filtered.slice(start, end).map((r) => p.renderRow(r, this._selectedIds)).join("");
    this._infoEl.textContent = total === 0 ? "0 produse" : `Afisezi ${start + 1}–${Math.min(end, total)} din ${total}`;
    this._prevEl.disabled = this._page === 0;
    this._nextEl.disabled = end >= total;
  }
}

const pagination = new PaginationController({
  pageSize: 50, tableBody: stocTableBody,
  infoEl: stocPageInfo, prevEl: stocPrevBtn, nextEl: stocNextBtn,
});

// ───────────── Platform switch ─────────────
function applyPlatform(name) {
  currentPlatform = name;
  p = PLATFORMS[name];

  // Reset state
  reportFile  = null;
  previewData = null;
  pagination.reset();
  previewSection.hidden = true;
  syncResults.hidden    = true;
  setStatus("", "");
  btnSync.disabled = true;
  stocSelectAll.checked = false;
  stocFilterEl.value    = "";
  stocSearchEl.value    = "";
  stocStatusFilterEl.hidden  = true;
  document.getElementById("nameReport").textContent = "";
  document.getElementById("dzReport").classList.remove("has-file");
  document.getElementById("fileReport").value = "";

  // History card — visible for both platforms, reset on switch
  exitHistoricalView();
  selectedHistorySessionId = null;
  btnHistoryLoad.disabled = true;
  loadSyncHistory();

  // Update labels
  pageDesc.textContent     = p.desc;
  btnPreview.textContent   = p.previewBtn;
  btnSync.textContent      = p.syncBtn;
  thSku.textContent        = p.skuLabel;
  thOldStock.textContent   = p.stockLabel;
  optNoSku.textContent     = p.noSkuFilter;
  optNoSku.value           = p.noSkuStatus;
  thExtra.hidden           = !p.hasExtra;

  // Restart connection check
  restartConn();
}

document.querySelectorAll('input[name="platform"]').forEach((radio) => {
  radio.addEventListener("change", () => applyPlatform(radio.value));
});

// ───────────── Connection dot ─────────────
function restartConn() {
  if (connTimer) { clearInterval(connTimer); connTimer = null; }
  document.removeEventListener("visibilitychange", _visChange);
  connCheck();
  connTimer = setInterval(connCheck, CONN_INTERVAL);
  document.addEventListener("visibilitychange", _visChange);
}
function _visChange() {
  if (document.hidden) { clearInterval(connTimer); connTimer = null; }
  else { connCheck(); connTimer = setInterval(connCheck, CONN_INTERVAL); }
}
async function connCheck() {
  connDot.className = "conn-dot conn-dot--loading";
  connDot.title = "Verific conexiunea...";
  try {
    const data = await fetch(p.connUrl).then((r) => r.json());
    if (data.ok) { connDot.className = "conn-dot conn-dot--ok"; connDot.title = `Conectat la ${currentPlatform === "emag" ? "eMAG" : "Shopify"} API`; }
    else         { connDot.className = "conn-dot conn-dot--error"; connDot.title = data.error || "Conexiune esuata"; }
  } catch (e) {
    connDot.className = "conn-dot conn-dot--error"; connDot.title = "Eroare retea: " + e.message;
  }
}

// ───────────── File upload ─────────────
(function () {
  const zone  = document.getElementById("dzReport");
  const input = document.getElementById("fileReport");
  const name  = document.getElementById("nameReport");
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("dragover"); if (e.dataTransfer.files.length) handle(e.dataTransfer.files[0]); });
  input.addEventListener("change", (e) => { if (e.target.files.length) handle(e.target.files[0]); });
  function handle(f) {
    name.textContent = `Selectat: ${f.name}`;
    zone.classList.add("has-file");
    reportFile = f;
    runPreview();
  }
})();

// ───────────── Sort headers ─────────────
function updateSortHeaders() {
  const { key, dir } = pagination.getSortState();
  document.querySelectorAll("#stocTable thead th[data-sort]").forEach((th) => {
    th.classList.toggle("sort-asc",  th.dataset.sort === key && dir === "asc");
    th.classList.toggle("sort-desc", th.dataset.sort === key && dir === "desc");
  });
}
document.querySelectorAll("#stocTable thead th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => { pagination.setSort(th.dataset.sort); updateSortHeaders(); });
});

stocFilterEl.addEventListener("change", () => pagination.setFilter(stocFilterEl.value));

function runSearch() {
  const q = stocSearchEl.value.trim();
  if (q.length > 0 && q.length < 3) return;
  pagination.setSearch(q);
}
btnStocSearch.addEventListener("click", runSearch);
stocSearchEl.addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });
stocSelectAll.addEventListener("change", () => pagination.selectAll(stocSelectAll.checked));
btnPreview.addEventListener("click", runPreview);
btnSync.addEventListener("click", runSync);

// ───────────── Preview ─────────────
async function runPreview() {
  exitHistoricalView();
  setStatus("", "");
  btnPreview.disabled  = true;
  btnPreview.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se incarca...';
  previewSection.hidden = true;
  syncResults.hidden    = true;

  const fd = new FormData();
  if (reportFile) fd.append("raport", reportFile);

  try {
    const resp = await fetch(p.previewUrl, { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || "Eroare necunoscuta", "error"); return; }
    previewData = data;
    renderPreview(data);
    setStatus(data.has_report ? p.previewMsg(data.summary) : `Gata. Date preluate din ${currentPlatform === "emag" ? "eMAG" : "Shopify"}.`, "success");
  } catch (e) {
    setStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnPreview.disabled  = false;
    btnPreview.textContent = p.previewBtn;
  }
}

function renderPreview(data) {
  const s = data.summary;
  if (data.has_report) {
    stocSummaryEl.className = "d-flex flex-wrap gap-2 mb-3";
    stocSummaryEl.innerHTML = p.renderSummary(s);
  } else {
    stocSummaryEl.className = "emag-summary-inline mb-2";
    stocSummaryEl.innerHTML = p.renderSummaryNoReport(s);
  }

  document.querySelector(".emag-table-wrap").classList.toggle("table--emag-only", !data.has_report);
  btnSync.disabled     = !data.has_report;
  stocStatusFilterEl.hidden = !data.has_report;
  if (!data.has_report) stocFilterEl.value = "";

  pagination.setRows(data.rows);
  updateSortHeaders();

  const blocks = data.has_report ? p.renderIssues(data) : [];
  stocIssuesEl.innerHTML = blocks.join("");
  bindIssueHeads(stocIssuesEl);

  previewSection.hidden = false;
}

// ───────────── Sync ─────────────
async function runSync() {
  const selected = pagination.getSelectedRows();
  if (!selected.length) { setStatus("Nicio linie selectata pentru sincronizare.", "error"); return; }

  const changed = selected.filter((r) => r.new_stock != null && r.new_stock !== r.old_stock);
  if (!changed.length) { setStatus("Niciun stoc modificat. Nimic de sincronizat.", "warning"); return; }

  const skipped = selected.length - changed.length;
  setStatus("", "");
  btnSync.disabled  = true;
  btnSync.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se trimit...';

  try {
    const resp = await fetch(p.syncUrl, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(p.buildPayload(changed, reportFile ? reportFile.name : "")),
    });
    const data = await resp.json();
    if (!resp.ok) { setStatus(data.error || "Eroare necunoscuta", "error"); return; }
    renderSyncResults(data, skipped);
    await loadSyncHistory();
    const skipNote = skipped > 0 ? ` (${skipped} nemodificate, sarite)` : "";
    setStatus(`Sincronizare finalizata: ${data.success_count} succes, ${data.error_count} erori${skipNote}.`,
      data.error_count ? "warning" : "success");
  } catch (e) {
    setStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnSync.disabled   = false;
    btnSync.textContent = p.syncBtn;
  }
}

function renderSyncResults(data) {
  const errors = data.results.filter((r) => !r.ok);
  syncSummaryEl.innerHTML = `
    <div class="stat success"><div class="label">Actualizate cu succes</div><div class="value">${data.success_count}</div></div>
    <div class="stat ${data.error_count ? "warning" : "muted"}"><div class="label">Erori</div><div class="value">${data.error_count}</div></div>`;
  syncErrorsEl.innerHTML = errors.length
    ? issueBlock("warning", "Produse care nu au putut fi actualizate", errors.map((r) => p.syncErrorLabel(r)))
    : "";
  bindIssueHeads(syncErrorsEl);
  syncResults.hidden = false;
}

function setStatus(msg, kind) {
  stocStatusEl.textContent = msg;
  stocStatusEl.className   = "status" + (kind ? " " + kind : "");
}

// ───────────── Init ─────────────
applyPlatform("emag");
