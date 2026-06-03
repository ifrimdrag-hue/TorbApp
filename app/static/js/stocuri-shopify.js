// ───────────── File upload helpers ─────────────
function setupDropzone(zoneId, inputId, nameId, onChange) {
  const zone  = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const name  = document.getElementById(nameId);
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    if (e.dataTransfer.files.length) handle(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", (e) => { if (e.target.files.length) handle(e.target.files[0]); });
  function handle(f) {
    name.textContent = `Selectat: ${f.name}`;
    zone.classList.add("has-file");
    onChange(f);
  }
}

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

// ───────────── Shopify connection indicator ─────────────
const SHOP_CONN_INTERVAL_MS = 3 * 60 * 1000;
const shopConnDot = document.getElementById("shopConnDot");
let _shopConnTimer = null;

function shopConnStart() {
  shopConnStop();
  shopConnCheck();
  _shopConnTimer = setInterval(shopConnCheck, SHOP_CONN_INTERVAL_MS);
  document.addEventListener("visibilitychange", _shopVisChange);
}
function shopConnStop() {
  clearInterval(_shopConnTimer);
  _shopConnTimer = null;
  document.removeEventListener("visibilitychange", _shopVisChange);
}
function _shopVisChange() {
  if (document.hidden) { clearInterval(_shopConnTimer); _shopConnTimer = null; }
  else { shopConnCheck(); _shopConnTimer = setInterval(shopConnCheck, SHOP_CONN_INTERVAL_MS); }
}
async function shopConnCheck() {
  _setConnDot("loading", "Verific conexiunea Shopify...");
  try {
    const resp = await fetch("/api/stocuri/shopify/connection-test");
    const data = await resp.json();
    if (data.ok) _setConnDot("ok", "Conectat la Shopify API");
    else _setConnDot("error", data.error || "Conexiune esuata");
  } catch (e) {
    _setConnDot("error", "Eroare retea: " + e.message);
  }
}
function _setConnDot(state, title) {
  shopConnDot.className = "conn-dot conn-dot--" + state;
  shopConnDot.title = title;
}
shopConnStart();

// ───────────── Stocuri / Shopify flow ─────────────
let shopReportFile   = null;
let shopPreviewData  = null;

const btnShopPreview     = document.getElementById("btnShopPreview");
const btnShopSync        = document.getElementById("btnShopSync");
const shopStatusEl       = document.getElementById("shopStatus");
const shopPreviewSection = document.getElementById("shopPreviewSection");
const shopSummaryEl      = document.getElementById("shopSummary");
const shopTableBody      = document.getElementById("shopTableBody");
const shopIssuesEl       = document.getElementById("shopIssues");
const shopSyncResults    = document.getElementById("shopSyncResults");
const shopSyncSummaryEl  = document.getElementById("shopSyncSummary");
const shopSyncErrorsEl   = document.getElementById("shopSyncErrors");
const shopSelectAll      = document.getElementById("shopSelectAll");
const shopToolbarEl      = document.getElementById("shopToolbar");
const shopFilterEl       = document.getElementById("shopFilter");
const shopPaginationInfo = document.getElementById("shopPaginationInfo");
const shopPrevPageBtn    = document.getElementById("shopPrevPage");
const shopNextPageBtn    = document.getElementById("shopNextPage");

// ───────────── PaginationController ─────────────
class PaginationController {
  constructor({ pageSize, tableBody, infoEl, prevEl, nextEl }) {
    this._all = []; this._filtered = []; this._selectedIds = new Set();
    this._page = 0; this._pageSize = pageSize;
    this._tableBody = tableBody; this._infoEl = infoEl;
    this._prevEl = prevEl; this._nextEl = nextEl;
    this._sortKey = null; this._sortDir = "asc";
    prevEl.addEventListener("click", () => this._goTo(this._page - 1));
    nextEl.addEventListener("click", () => this._goTo(this._page + 1));
    tableBody.addEventListener("change", (e) => {
      const cb = e.target.closest(".shop-row-check");
      if (!cb) return;
      if (cb.checked) this._selectedIds.add(cb.dataset.itemId);
      else            this._selectedIds.delete(cb.dataset.itemId);
    });
  }
  setRows(rows) {
    this._all = rows;
    this._filtered = [...rows];
    this._selectedIds = new Set(
      rows
        .filter((r) => r.new_stock !== null && r.new_stock !== undefined && r.new_stock !== r.old_stock)
        .map((r) => r.inventory_item_id)
    );
    this._applySort();
    this._goTo(0);
  }
  setFilter(status) {
    if (status === "updated") {
      this._filtered = this._all.filter((r) => r.new_stock !== null && r.new_stock !== undefined && r.new_stock !== r.old_stock);
    } else {
      this._filtered = status ? this._all.filter((r) => r.status === status) : [...this._all];
    }
    this._applySort();
    this._goTo(0);
  }
  setSort(key) {
    this._sortDir = this._sortKey === key && this._sortDir === "asc" ? "desc" : "asc";
    this._sortKey = key;
    this._applySort();
    this._goTo(0);
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
      if (checked) this._selectedIds.add(r.inventory_item_id);
      else         this._selectedIds.delete(r.inventory_item_id);
    });
    this._renderPage();
  }
  getSelectedRows() { return this._all.filter((r) => this._selectedIds.has(r.inventory_item_id)); }
  _goTo(page) {
    const total = this._filtered.length;
    this._page = Math.max(0, Math.min(page, Math.max(0, Math.ceil(total / this._pageSize) - 1)));
    this._renderPage();
  }
  _renderPage() {
    const total = this._filtered.length, start = this._page * this._pageSize, end = start + this._pageSize;
    this._tableBody.innerHTML = this._filtered.slice(start, end).map((r) => renderShopRow(r, this._selectedIds)).join("");
    this._infoEl.textContent = total === 0 ? "0 produse" : `Afisezi ${start + 1}–${Math.min(end, total)} din ${total} produse`;
    this._prevEl.disabled = this._page === 0;
    this._nextEl.disabled = end >= total;
  }
}

const SHOP_STATUS_LABEL = {
  updated:          '<span class="badge bg-success">Actualizat</span>',
  zeroed_threshold: '<span class="badge bg-warning text-dark">Zerificate (stoc mic)</span>',
  unchanged:        '<span class="badge bg-secondary">Nemodificat</span>',
  no_sku:           '<span class="badge bg-secondary">Fara SKU</span>',
  no_report:        '<span class="badge bg-secondary">–</span>',
};

function renderShopRow(r, selectedIds) {
  const canUpdate    = r.status === "updated" || r.status === "zeroed_threshold";
  const isChecked    = selectedIds && selectedIds.has(r.inventory_item_id);
  const newStockCell = r.new_stock !== null && r.new_stock !== undefined ? r.new_stock : '<span class="text-secondary">–</span>';
  return `<tr class="emag-row emag-row--${r.status}">
    <td><input type="checkbox" class="shop-row-check"
         data-item-id="${escapeHtml(r.inventory_item_id)}"
         ${canUpdate ? (isChecked ? "checked" : "") : "disabled"} /></td>
    <td class="emag-name">${escapeHtml(r.name)}</td>
    <td><code>${escapeHtml(r.sku || "—")}</code></td>
    <td style="text-align:right;">${r.old_stock}</td>
    <td style="text-align:right;">${newStockCell}</td>
    <td>${SHOP_STATUS_LABEL[r.status] || escapeHtml(r.status)}</td>
  </tr>`;
}

setupDropzone("dzShopReport", "fileShopReport", "nameShopReport", (f) => {
  shopReportFile = f;
  runShopPreview();
});

const shopPagination = new PaginationController({
  pageSize: 50, tableBody: shopTableBody,
  infoEl: shopPaginationInfo, prevEl: shopPrevPageBtn, nextEl: shopNextPageBtn,
});

shopFilterEl.addEventListener("change", () => shopPagination.setFilter(shopFilterEl.value));

function updateShopSortHeaders() {
  const { key, dir } = shopPagination.getSortState();
  document.querySelectorAll("#shopTable thead th[data-sort]").forEach((th) => {
    th.classList.toggle("sort-asc",  th.dataset.sort === key && dir === "asc");
    th.classList.toggle("sort-desc", th.dataset.sort === key && dir === "desc");
  });
}
document.querySelectorAll("#shopTable thead th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => { shopPagination.setSort(th.dataset.sort); updateShopSortHeaders(); });
});

btnShopPreview.addEventListener("click", runShopPreview);
btnShopSync.addEventListener("click", runShopSync);
shopSelectAll.addEventListener("change", () => shopPagination.selectAll(shopSelectAll.checked));

async function runShopPreview() {
  setShopStatus("", "");
  btnShopPreview.disabled  = true;
  btnShopPreview.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se incarca...';
  shopPreviewSection.hidden = true;
  shopSyncResults.hidden    = true;

  const fd = new FormData();
  if (shopReportFile) fd.append("raport", shopReportFile);

  try {
    const resp = await fetch("/api/stocuri/shopify/preview", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) { setShopStatus(data.error || "Eroare necunoscuta", "error"); return; }
    shopPreviewData = data;
    renderShopPreview(data);
    const msg = data.has_report
      ? `Gata. ${data.summary.to_update} produse vor fi actualizate. Verifica tabelul si apasa Sincronizeaza.`
      : `Gata. ${data.summary.total_shopify_items} produse preluate din Shopify.`;
    setShopStatus(msg, "success");
  } catch (e) {
    setShopStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnShopPreview.disabled  = false;
    btnShopPreview.textContent = "Incarca stoc Shopify";
  }
}

function renderShopPreview(data) {
  const s = data.summary;
  if (data.has_report) {
    shopSummaryEl.className = "d-flex flex-wrap gap-2 mb-3";
    shopSummaryEl.innerHTML = `
      <div class="stat"><div class="label">Total Shopify</div><div class="value">${s.total_shopify_items}</div></div>
      <div class="stat success"><div class="label">De actualizat (stoc real)</div><div class="value">${s.updated_with_stock}</div></div>
      <div class="stat warning"><div class="label">Zerificate (stoc &le; ${s.safety_threshold})</div><div class="value">${s.zeroed_threshold}</div></div>
      <div class="stat muted"><div class="label">Nemodificate</div><div class="value">${s.unchanged}</div></div>
      <div class="stat muted"><div class="label">Fara SKU pe Shopify</div><div class="value">${s.no_sku}</div></div>
      <div class="stat muted"><div class="label">SKU-uri negasite pe Shopify</div><div class="value">${s.not_in_shopify}</div></div>
    `;
  } else {
    shopSummaryEl.className = "emag-summary-inline mb-2";
    shopSummaryEl.innerHTML = `${s.total_shopify_items} produse preluate din Shopify` +
      (s.no_sku > 0 ? ` &middot; <span class="emag-summary-warn">${s.no_sku} fara SKU</span>` : "");
  }

  document.querySelector(".emag-table-wrap").classList.toggle("table--emag-only", !data.has_report);
  btnShopSync.disabled  = !data.has_report;
  shopToolbarEl.hidden  = !data.has_report;
  if (!data.has_report) shopFilterEl.value = "";

  shopPagination.setRows(data.rows);
  updateShopSortHeaders();

  const blocks = [];
  if (data.has_report) {
    if (data.warnings && data.warnings.length)
      blocks.push(issueBlock("warning", "Avertismente parsare raport", data.warnings));
    if (data.skus_not_in_shopify && data.skus_not_in_shopify.length)
      blocks.push(issueBlock("warning", "SKU-uri din raport negasite pe Shopify",
        data.skus_not_in_shopify.map((r) => `codmare ${r.codmare} — qty ${r.qty}`)));
  }
  shopIssuesEl.innerHTML = blocks.join("");
  shopIssuesEl.querySelectorAll(".issue-head").forEach((h) =>
    h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; })
  );
  shopPreviewSection.hidden = false;
}

async function runShopSync() {
  const selectedRows = shopPagination.getSelectedRows();
  if (!selectedRows.length) { setShopStatus("Nicio linie selectata pentru sincronizare.", "error"); return; }

  const changed = selectedRows.filter(
    (r) => r.new_stock !== null && r.new_stock !== undefined && r.new_stock !== r.old_stock
  );
  if (!changed.length) { setShopStatus("Niciun stoc modificat fata de Shopify. Nimic de sincronizat.", "warning"); return; }

  const skipped = selectedRows.length - changed.length;
  const rows_to_update = changed.map((r) => ({
    inventory_item_id: r.inventory_item_id,
    sku:       r.sku || "",
    name:      r.name,
    new_stock: r.new_stock,
  }));

  setShopStatus("", "");
  btnShopSync.disabled  = true;
  btnShopSync.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se trimit...';

  try {
    const resp = await fetch("/api/stocuri/shopify/sync", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows_to_update }),
    });
    const data = await resp.json();
    if (!resp.ok) { setShopStatus(data.error || "Eroare necunoscuta", "error"); return; }
    renderSyncResults(data);
    const skipNote = skipped > 0 ? ` (${skipped} nemodificate, sarite)` : "";
    setShopStatus(
      `Sincronizare finalizata: ${data.success_count} succes, ${data.error_count} erori${skipNote}.`,
      data.error_count ? "warning" : "success"
    );
  } catch (e) {
    setShopStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnShopSync.disabled   = false;
    btnShopSync.textContent = "Sincronizeaza pe Shopify";
  }
}

function renderSyncResults(data) {
  const errors = data.results.filter((r) => !r.ok);
  shopSyncSummaryEl.innerHTML = `
    <div class="stat success"><div class="label">Actualizate cu succes</div><div class="value">${data.success_count}</div></div>
    <div class="stat ${data.error_count ? "warning" : "muted"}"><div class="label">Erori</div><div class="value">${data.error_count}</div></div>
  `;
  shopSyncErrorsEl.innerHTML = errors.length
    ? issueBlock("warning", "Produse care nu au putut fi actualizate",
        errors.map((r) => `${r.name} (SKU ${r.sku || "—"}): ${r.error}`))
    : "";
  if (errors.length)
    shopSyncErrorsEl.querySelectorAll(".issue-head").forEach((h) =>
      h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; })
    );
  shopSyncResults.hidden = false;
}

function setShopStatus(msg, kind) {
  if (kind === "busy") {
    shopStatusEl.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${escapeHtml(msg)}`;
  } else {
    shopStatusEl.textContent = msg;
  }
  shopStatusEl.className = "status" + (kind ? " " + kind : "");
}
