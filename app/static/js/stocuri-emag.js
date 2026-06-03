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
  input.addEventListener("change", (e) => {
    if (e.target.files.length) handle(e.target.files[0]);
  });

  function handle(f) {
    name.textContent = `Selectat: ${f.name}`;
    zone.classList.add("has-file");
    onChange(f);
  }
}

// ───────────── eMAG connection indicator ─────────────
const EMAG_CONN_INTERVAL_MS = 3 * 60 * 1000;
const emagConnDot = document.getElementById("emagConnDot");
let _emagConnTimer = null;

function emagConnStart() {
  emagConnStop();
  emagConnCheck();
  _emagConnTimer = setInterval(emagConnCheck, EMAG_CONN_INTERVAL_MS);
  document.addEventListener("visibilitychange", _emagVisibilityChange);
}

function emagConnStop() {
  clearInterval(_emagConnTimer);
  _emagConnTimer = null;
  document.removeEventListener("visibilitychange", _emagVisibilityChange);
}

function _emagVisibilityChange() {
  if (document.hidden) {
    clearInterval(_emagConnTimer);
    _emagConnTimer = null;
  } else {
    emagConnCheck();
    _emagConnTimer = setInterval(emagConnCheck, EMAG_CONN_INTERVAL_MS);
  }
}

async function emagConnCheck() {
  _setConnDot("loading", "Verific conexiunea eMAG...");
  try {
    const resp = await fetch("/api/stocuri/emag/connection-test");
    const data = await resp.json();
    if (data.ok) {
      _setConnDot("ok", "Conectat la eMAG API");
    } else {
      _setConnDot("error", data.error || "Conexiune esuata");
    }
  } catch (e) {
    _setConnDot("error", "Eroare retea: " + e.message);
  }
}

function _setConnDot(state, title) {
  emagConnDot.className = "conn-dot conn-dot--" + state;
  emagConnDot.title = title;
}

emagConnStart();

// ───────────── Stocuri / eMAG flow ─────────────
let emagReportFile = null;
let emagPreviewData = null;

const btnEmagPreview       = document.getElementById("btnEmagPreview");
const btnEmagSync          = document.getElementById("btnEmagSync");
const emagStatusEl         = document.getElementById("emagStatus");
const emagPreviewSection   = document.getElementById("emagPreviewSection");
const emagSummaryEl        = document.getElementById("emagSummary");
const emagTableBody        = document.getElementById("emagTableBody");
const emagIssuesEl         = document.getElementById("emagIssues");
const emagSyncResults      = document.getElementById("emagSyncResults");
const emagSyncSummaryEl    = document.getElementById("emagSyncSummary");
const emagSyncErrorsEl     = document.getElementById("emagSyncErrors");
const emagSelectAll        = document.getElementById("emagSelectAll");
const emagToolbarEl        = document.getElementById("emagToolbar");
const emagFilterEl         = document.getElementById("emagFilter");
const emagPaginationInfoEl = document.getElementById("emagPaginationInfo");
const emagPrevPageBtn      = document.getElementById("emagPrevPage");
const emagNextPageBtn      = document.getElementById("emagNextPage");

// ───────────── PaginationController ─────────────
class PaginationController {
  constructor({ pageSize, tableBody, infoEl, prevEl, nextEl }) {
    this._all         = [];
    this._filtered    = [];
    this._selectedIds = new Set();
    this._page        = 0;
    this._pageSize    = pageSize;
    this._tableBody   = tableBody;
    this._infoEl      = infoEl;
    this._prevEl      = prevEl;
    this._nextEl      = nextEl;
    this._sortKey     = null;
    this._sortDir     = "asc";

    prevEl.addEventListener("click", () => this._goTo(this._page - 1));
    nextEl.addEventListener("click", () => this._goTo(this._page + 1));

    tableBody.addEventListener("change", (e) => {
      const cb = e.target.closest(".emag-row-check");
      if (!cb) return;
      const id = cb.dataset.offerId;
      if (cb.checked) this._selectedIds.add(id);
      else            this._selectedIds.delete(id);
    });
  }

  setRows(rows) {
    this._all      = rows;
    this._filtered = [...rows];
    this._selectedIds = new Set(
      rows
        .filter((r) => r.new_stock !== null && r.new_stock !== undefined && r.new_stock !== r.old_stock)
        .map((r) => String(r.offer_id))
    );
    this._applySort();
    this._goTo(0);
  }

  setFilter(status) {
    if (status === "updated") {
      this._filtered = this._all.filter(
        (r) => r.new_stock !== null && r.new_stock !== undefined && r.new_stock !== r.old_stock
      );
    } else {
      this._filtered = status
        ? this._all.filter((r) => r.status === status)
        : [...this._all];
    }
    this._applySort();
    this._goTo(0);
  }

  setSort(key) {
    if (this._sortKey === key) {
      this._sortDir = this._sortDir === "asc" ? "desc" : "asc";
    } else {
      this._sortKey = key;
      this._sortDir = "asc";
    }
    this._applySort();
    this._goTo(0);
  }

  getSortState() {
    return { key: this._sortKey, dir: this._sortDir };
  }

  _applySort() {
    if (!this._sortKey) return;
    const key = this._sortKey;
    const dir = this._sortDir === "asc" ? 1 : -1;
    this._filtered = [...this._filtered].sort((a, b) => {
      let av = a[key], bv = b[key];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "string") return av.localeCompare(bv, "ro") * dir;
      return (av - bv) * dir;
    });
  }

  selectAll(checked) {
    this._filtered.forEach((r) => {
      const canUpdate = r.status === "updated" || r.status === "zeroed_threshold";
      if (!canUpdate) return;
      if (checked) this._selectedIds.add(String(r.offer_id));
      else         this._selectedIds.delete(String(r.offer_id));
    });
    this._renderPage();
  }

  getSelectedRows() {
    return this._all.filter((r) => this._selectedIds.has(String(r.offer_id)));
  }

  _goTo(page) {
    const total   = this._filtered.length;
    const maxPage = Math.max(0, Math.ceil(total / this._pageSize) - 1);
    this._page    = Math.max(0, Math.min(page, maxPage));
    this._renderPage();
  }

  _renderPage() {
    const total = this._filtered.length;
    const start = this._page * this._pageSize;
    const end   = start + this._pageSize;
    const slice = this._filtered.slice(start, end);

    this._tableBody.innerHTML = slice
      .map((r) => renderEmagRow(r, this._selectedIds))
      .join("");

    this._infoEl.textContent =
      total === 0
        ? "0 oferte"
        : `Afisezi ${start + 1}–${Math.min(end, total)} din ${total} oferte`;

    this._prevEl.disabled = this._page === 0;
    this._nextEl.disabled = end >= total;
  }
}

function renderEmagRow(r, selectedIds) {
  const canUpdate    = r.status === "updated" || r.status === "zeroed_threshold";
  const isChecked    = selectedIds && selectedIds.has(String(r.offer_id));
  const newStockCell =
    r.new_stock !== null && r.new_stock !== undefined
      ? r.new_stock
      : '<span class="text-secondary">–</span>';
  return `<tr class="emag-row emag-row--${r.status}">
    <td><input type="checkbox" class="emag-row-check"
         data-offer-id="${r.offer_id}"
         data-ean="${escapeHtml(r.ean || "")}"
         data-name="${escapeHtml(r.name)}"
         data-new-stock="${r.new_stock ?? ""}"
         ${canUpdate ? (isChecked ? "checked" : "") : "disabled"} /></td>
    <td class="emag-name">${escapeHtml(r.name)}</td>
    <td><code>${escapeHtml(r.ean || "—")}</code></td>
    <td><code>${escapeHtml(r.part_number_key || "—")}</code></td>
    <td style="text-align:right;">${r.old_stock}</td>
    <td style="text-align:right;">${newStockCell}</td>
    <td>${EMAG_STATUS_LABEL[r.status] || escapeHtml(r.status)}</td>
  </tr>`;
}

setupDropzone("dzReport", "fileReport", "nameReport", (f) => {
  emagReportFile = f;
  runEmagPreview();
});

const emagPagination = new PaginationController({
  pageSize:  50,
  tableBody: emagTableBody,
  infoEl:    emagPaginationInfoEl,
  prevEl:    emagPrevPageBtn,
  nextEl:    emagNextPageBtn,
});

emagFilterEl.addEventListener("change", () => {
  emagPagination.setFilter(emagFilterEl.value);
});

function updateEmagSortHeaders() {
  const { key, dir } = emagPagination.getSortState();
  document.querySelectorAll("#emagTable thead th[data-sort]").forEach((th) => {
    th.classList.toggle("sort-asc",  th.dataset.sort === key && dir === "asc");
    th.classList.toggle("sort-desc", th.dataset.sort === key && dir === "desc");
  });
}

document.querySelectorAll("#emagTable thead th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    emagPagination.setSort(th.dataset.sort);
    updateEmagSortHeaders();
  });
});

btnEmagPreview.addEventListener("click", runEmagPreview);
btnEmagSync.addEventListener("click", runEmagSync);

emagSelectAll.addEventListener("change", () => {
  emagPagination.selectAll(emagSelectAll.checked);
});

async function runEmagPreview() {
  setEmagStatus("", "");
  btnEmagPreview.disabled   = true;
  btnEmagPreview.innerHTML  = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se incarca...';
  emagPreviewSection.hidden = true;
  emagSyncResults.hidden    = true;

  const fd = new FormData();
  if (emagReportFile) fd.append("raport", emagReportFile);

  try {
    const resp = await fetch("/api/stocuri/emag/preview", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      setEmagStatus(data.error || "Eroare necunoscuta", "error");
      return;
    }
    emagPreviewData = data;
    renderEmagPreview(data);
    const msg = data.has_report
      ? `Gata. ${data.summary.to_update} oferte vor fi actualizate. Verifica tabelul si apasa Sincronizeaza.`
      : `Gata. ${data.summary.total_emag_offers} oferte preluate din eMAG.`;
    setEmagStatus(msg, "success");
  } catch (e) {
    setEmagStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnEmagPreview.disabled   = false;
    btnEmagPreview.textContent = "Incarca stoc emag";
  }
}

const EMAG_STATUS_LABEL = {
  updated:           '<span class="badge bg-success">Actualizat</span>',
  zeroed_threshold:  '<span class="badge bg-warning text-dark">Zerificate (stoc mic)</span>',
  unchanged:         '<span class="badge bg-secondary">Nemodificat</span>',
  no_ean:            '<span class="badge bg-secondary">Fara EAN</span>',
  no_report:         '<span class="badge bg-secondary">–</span>',
};

function renderEmagPreview(data) {
  const hasReport = data.has_report;
  const s         = data.summary;

  if (hasReport) {
    emagSummaryEl.className = "d-flex flex-wrap gap-2 mb-3";
    emagSummaryEl.innerHTML = `
      <div class="stat"><div class="label">Total oferte eMAG</div><div class="value">${s.total_emag_offers}</div></div>
      <div class="stat success"><div class="label">De actualizat (stoc real)</div><div class="value">${s.updated_with_stock}</div></div>
      <div class="stat warning"><div class="label">Zerificate (stoc &le; ${s.safety_threshold})</div><div class="value">${s.zeroed_threshold}</div></div>
      <div class="stat muted"><div class="label">Nemodificate</div><div class="value">${s.unchanged}</div></div>
      <div class="stat muted"><div class="label">Fara EAN pe eMAG</div><div class="value">${s.no_ean}</div></div>
      <div class="stat muted"><div class="label">SKU-uri negasite pe eMAG</div><div class="value">${s.not_in_emag}</div></div>
    `;
  } else {
    emagSummaryEl.className = "emag-summary-inline mb-2";
    emagSummaryEl.innerHTML =
      `${s.total_emag_offers} oferte preluate din eMAG` +
      (s.no_ean > 0 ? ` &middot; <span class="emag-summary-warn">${s.no_ean} fara EAN</span>` : "");
  }

  document.querySelector(".emag-table-wrap")
    .classList.toggle("table--emag-only", !hasReport);

  btnEmagSync.disabled = !hasReport;
  emagToolbarEl.hidden = !hasReport;
  if (!hasReport) emagFilterEl.value = "";

  emagPagination.setRows(data.rows);
  updateEmagSortHeaders();

  const blocks = [];
  if (hasReport) {
    if (data.warnings && data.warnings.length) {
      blocks.push(issueBlock("warning", "Avertismente parsare raport", data.warnings));
    }
    if (data.skus_not_in_emag && data.skus_not_in_emag.length) {
      blocks.push(issueBlock(
        "warning",
        "SKU-uri din raport negasite pe eMAG",
        data.skus_not_in_emag.map((r) => `SKU ${r.sku} — EAN ${r.ean} — qty ${r.qty}`)
      ));
    }
  }
  emagIssuesEl.innerHTML = blocks.join("");
  emagIssuesEl.querySelectorAll(".issue-head").forEach((h) => {
    h.addEventListener("click", () => {
      h.nextElementSibling.hidden = !h.nextElementSibling.hidden;
    });
  });

  emagPreviewSection.hidden = false;
}

async function runEmagSync() {
  const selectedRows = emagPagination.getSelectedRows();
  if (!selectedRows.length) {
    setEmagStatus("Nicio linie selectata pentru sincronizare.", "error");
    return;
  }

  const changed = selectedRows.filter(
    (r) => r.new_stock !== null && r.new_stock !== undefined && r.new_stock !== r.old_stock
  );

  if (!changed.length) {
    setEmagStatus("Niciun stoc modificat fata de eMAG. Nimic de sincronizat.", "warning");
    return;
  }

  const skipped = selectedRows.length - changed.length;
  const rows_to_update = changed.map((r) => ({
    offer_id:        r.offer_id,
    ean:             r.ean || "",
    name:            r.name,
    new_stock:       r.new_stock,
    part_number_key: r.part_number_key || "",
  }));

  setEmagStatus("", "");
  btnEmagSync.disabled = true;
  btnEmagSync.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se trimit...';

  try {
    const resp = await fetch("/api/stocuri/emag/sync", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ rows_to_update }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      setEmagStatus(data.error || "Eroare necunoscuta", "error");
      return;
    }
    renderSyncResults(data);
    const skipNote = skipped > 0 ? ` (${skipped} nemodificate, sarite)` : "";
    setEmagStatus(
      `Sincronizare finalizata: ${data.success_count} succes, ${data.error_count} erori${skipNote}.`,
      data.error_count ? "warning" : "success"
    );
  } catch (e) {
    setEmagStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnEmagSync.disabled  = false;
    btnEmagSync.textContent = "Sincronizeaza pe eMAG";
  }
}

function renderSyncResults(data) {
  const errors = data.results.filter((r) => !r.ok);
  emagSyncSummaryEl.innerHTML = `
    <div class="stat success"><div class="label">Actualizate cu succes</div><div class="value">${data.success_count}</div></div>
    <div class="stat ${data.error_count ? "warning" : "muted"}"><div class="label">Erori</div><div class="value">${data.error_count}</div></div>
  `;
  emagSyncErrorsEl.innerHTML = errors.length
    ? issueBlock("warning", "Oferte care nu au putut fi actualizate",
        errors.map((r) => `${r.name} (EAN ${r.ean || "—"}): ${r.error}`))
    : "";
  if (errors.length) {
    emagSyncErrorsEl.querySelectorAll(".issue-head").forEach((h) => {
      h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; });
    });
  }
  emagSyncResults.hidden = false;
}

function setEmagStatus(msg, kind) {
  if (kind === "busy") {
    emagStatusEl.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${escapeHtml(msg)}`;
  } else {
    emagStatusEl.textContent = msg;
  }
  emagStatusEl.className = "status" + (kind ? " " + kind : "");
}

function issueBlock(kind, title, items) {
  const list = items.slice(0, 200).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const more = items.length > 200
    ? `<div class="text-secondary mt-1">… si inca ${items.length - 200}</div>`
    : "";
  return `
    <div class="issue-block mb-2">
      <div class="issue-head ${kind} d-flex justify-content-between align-items-center p-2 rounded" style="cursor:pointer;">
        <span>${escapeHtml(title)}</span>
        <span class="badge bg-secondary">${items.length}</span>
      </div>
      <div class="issue-body p-2" hidden>
        <ul class="mb-0">${list}</ul>
        ${more}
      </div>
    </div>
  `;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
