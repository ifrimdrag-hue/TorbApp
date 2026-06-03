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
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
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

function triggerDownload(b64, filename, mime) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const blob  = new Blob([bytes], { type: mime || "text/csv" });
  const url   = URL.createObjectURL(blob);
  const a     = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 300);
}

// ───────────── Stocuri / Shopify flow ─────────────
let shopReportFile    = null;
let shopInventoryFile = null;
let shopLastResult    = null;

const btnRunShop      = document.getElementById("btnRunShop");
const btnDownloadShop = document.getElementById("btnDownloadShop");
const statusShopEl    = document.getElementById("statusShop");
const resultShopEl    = document.getElementById("resultShop");
const summaryShopEl   = document.getElementById("summaryShop");
const issuesShopEl    = document.getElementById("issuesShop");

setupDropzone("dzShopReport", "fileShopReport", "nameShopReport", (f) => {
  shopReportFile = f;
  btnRunShop.disabled = !(shopReportFile && shopInventoryFile);
});
setupDropzone("dzShopInventory", "fileShopInventory", "nameShopInventory", (f) => {
  shopInventoryFile = f;
  btnRunShop.disabled = !(shopReportFile && shopInventoryFile);
});

btnRunShop.addEventListener("click", runShop);
btnDownloadShop.addEventListener("click", () => {
  if (shopLastResult) triggerDownload(shopLastResult.file_b64, shopLastResult.filename, "text/csv");
});

async function runShop() {
  setStatusShop("Procesez fisierele...", "busy");
  btnRunShop.disabled  = true;
  btnRunShop.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Procesez...';
  resultShopEl.hidden  = true;

  const fd = new FormData();
  fd.append("raport", shopReportFile);
  fd.append("inventory", shopInventoryFile);

  try {
    const resp = await fetch("/api/stocuri/shopify/run", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      setStatusShop(data.error || "Eroare necunoscuta", "error");
      return;
    }
    shopLastResult = data;
    renderShopResult(data);
    setStatusShop("Gata. Verifica sumarul si descarca CSV-ul.", "success");
  } catch (e) {
    setStatusShop("Eroare retea: " + e.message, "error");
  } finally {
    btnRunShop.disabled  = !(shopReportFile && shopInventoryFile);
    btnRunShop.textContent = "Genereaza CSV pentru Shopify";
  }
}

function setStatusShop(msg, kind) {
  if (kind === "busy") {
    statusShopEl.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${escapeHtml(msg)}`;
  } else {
    statusShopEl.textContent = msg;
  }
  statusShopEl.className = "status" + (kind ? " " + kind : "");
}

function renderShopResult(data) {
  resultShopEl.hidden = false;
  const s = data.summary;
  summaryShopEl.innerHTML = `
    <div class="stat"><div class="label">Randuri raport</div><div class="value">${s.report_total_rows}</div></div>
    <div class="stat"><div class="label">SKU-uri cu codmare</div><div class="value">${s.report_skus_with_codmare}</div></div>
    <div class="stat success"><div class="label">Active pe Shopify</div><div class="value">${s.shopify_active}</div></div>
    <div class="stat warning"><div class="label">Zerificate: stoc &le; ${s.safety_threshold}</div><div class="value">${s.shopify_zero_low_stock}</div></div>
    <div class="stat warning"><div class="label">Zerificate: nu sunt in raport</div><div class="value">${s.shopify_zero_not_in_report}</div></div>
    <div class="stat muted"><div class="label">Codmare negasit pe Shopify</div><div class="value">${s.codmare_not_in_shopify}</div></div>
    <div class="stat muted"><div class="label">Randuri alte locatii (neatinse)</div><div class="value">${s.shopify_rows_other_location}</div></div>
  `;
  const blocks = [];
  if (data.warnings && data.warnings.length)
    blocks.push(issueBlock("warning", "Avertismente parsare", data.warnings));
  if (data.codmare_below_threshold && data.codmare_below_threshold.length)
    blocks.push(issueBlock("warning", `Produse cu stoc mic (≤ ${s.safety_threshold}) — trimise ca 0 pe Shopify`,
      data.codmare_below_threshold.map((r) => `codmare ${r.codmare} — stoc real ${r.qty_real}`)));
  if (data.codmare_not_in_shopify && data.codmare_not_in_shopify.length)
    blocks.push(issueBlock("warning", "Codmare din raport care NU exista pe Shopify",
      data.codmare_not_in_shopify));
  if (data.skus_no_codmare && data.skus_no_codmare.length)
    blocks.push(issueBlock("warning", "SKU-uri fara codmare (sarite)",
      data.skus_no_codmare.map((r) => `SKU ${r.sku} — qty ${r.qty}`)));
  issuesShopEl.innerHTML = blocks.join("");
  issuesShopEl.querySelectorAll(".issue-head").forEach((h) => {
    h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; });
  });
}
