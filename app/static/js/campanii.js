// ───────────── Shared helpers ─────────────
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function triggerDownload(b64, filename, mime) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const blob  = new Blob([bytes], { type: mime || "application/octet-stream" });
  const url   = URL.createObjectURL(blob);
  const a     = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 300);
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

function setupDropzone(zoneId, inputId, nameId, onChange) {
  const zone  = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const name  = document.getElementById(nameId);
  if (!zone) return;
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
    if (name) name.textContent = `Selectat: ${f.name}`;
    zone.classList.add("has-file");
    onChange(f);
  }
}
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Campanii â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const TYPE_LABEL = {
  promo: "Promo", gifting: "Gifting", lansare: "Lansare", sezonier: "Sezonier", giveaway: "Giveaway",
};
const STATUS_LABEL = {
  draft: "Draft", planned: "Planificata", active: "Activa", completed: "Finalizata", cancelled: "Anulata",
};
const CHANNEL_LABEL = { shopify: "Shopify", emag: "eMAG", instagram: "Instagram", facebook: "Facebook" };

const campaignListEl  = document.getElementById("campaignList");
const campaignEmptyEl = document.getElementById("campaignEmpty");
const snapshotBarEl   = document.getElementById("snapshotBar");
const btnNewCampaign  = document.getElementById("btnNewCampaign");

const modalEl    = document.getElementById("campaignModal");
const modalTitle = document.getElementById("modalTitle");
const modalClose = document.getElementById("modalClose");
const formEl     = document.getElementById("campaignForm");
const formCancel = document.getElementById("formCancel");
const productSearchEl    = document.getElementById("productSearch");
const productSearchResults = document.getElementById("productSearchResults");
const campaignProductsEl = document.getElementById("campaignProducts");

let snapshotData = null;       // { available, uploaded_at, source_filename, rows: [...] }
let editingCampaignId = null;
let formProducts = [];         // current products in the form

btnNewCampaign.addEventListener("click", () => openModal());

// Export sedinta â€” PPTX + DOCX + XLSX in ZIP
const btnExportSedinta = document.getElementById("btnExportSedinta");
btnExportSedinta.addEventListener("click", exportSedinta);

// AI Campaign Generator
const btnAiGenerateCampaigns = document.getElementById("btnAiGenerateCampaigns");
btnAiGenerateCampaigns.addEventListener("click", openAiCampGenModal);
const aiCampGenModal = document.getElementById("aiCampGenModal");
const aiCampGenClose = document.getElementById("aiCampGenClose");
const aiCampGenSetup = document.getElementById("aiCampGenSetup");
const aiCampLoading = document.getElementById("aiCampLoading");
const aiCampError = document.getElementById("aiCampError");
const aiCampProposals = document.getElementById("aiCampProposals");
const btnAiCampGenerate = document.getElementById("btnAiCampGenerate");

aiCampGenClose.addEventListener("click", () => { aiCampGenModal.hidden = true; });
aiCampGenModal.addEventListener("click", (e) => { if (e.target === aiCampGenModal) aiCampGenModal.hidden = true; });
btnAiCampGenerate.addEventListener("click", runAiCampGen);

let lastAiProposals = null;

function openAiCampGenModal() {
  // Default period: next 4 weeks
  const today = new Date();
  const end = new Date(today.getTime() + 28 * 86400000);
  document.getElementById("aiCampStart").value = today.toISOString().slice(0, 10);
  document.getElementById("aiCampEnd").value = end.toISOString().slice(0, 10);
  document.getElementById("aiCampBudget").value = "1000";
  document.getElementById("aiCampGoal").value = "";
  document.getElementById("aiCampNotes").value = "";
  document.getElementById("aiCampNumCampaigns").value = "3";

  // Build brands checkboxes
  const box = document.getElementById("aiCampBrandsBox");
  box.innerHTML = BRANDS.map((b) =>
    `<label class="cb"><input type="checkbox" name="aiBrand" value="${escapeHtml(b)}" /> ${escapeHtml(b)}</label>`
  ).join("");

  aiCampGenSetup.hidden = false;
  aiCampLoading.hidden = true;
  aiCampError.hidden = true;
  aiCampProposals.hidden = true;
  aiCampProposals.innerHTML = "";
  lastAiProposals = null;
  btnAiCampGenerate.disabled = false;
  aiCampGenModal.hidden = false;
}

async function runAiCampGen() {
  const periodStart = document.getElementById("aiCampStart").value;
  const periodEnd = document.getElementById("aiCampEnd").value;
  const budget = Number(document.getElementById("aiCampBudget").value);
  const num = Number(document.getElementById("aiCampNumCampaigns").value);
  const goal = document.getElementById("aiCampGoal").value.trim();
  const notes = document.getElementById("aiCampNotes").value.trim();
  const brands = Array.from(document.querySelectorAll('input[name="aiBrand"]:checked')).map((cb) => cb.value);

  if (!periodStart || !periodEnd || !budget || !goal) {
    alert("Completeaza campurile obligatorii: perioada, buget, obiectiv.");
    return;
  }

  aiCampGenSetup.hidden = true;
  aiCampLoading.hidden = false;
  aiCampError.hidden = true;
  aiCampProposals.hidden = true;

  try {
    const resp = await fetch("/api/campanii/ai-generate-proposals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        period_start: periodStart, period_end: periodEnd,
        total_budget: budget, num_campaigns: num,
        goal, brands_focus: brands, notes,
      }),
    });
    const data = await resp.json();
    aiCampLoading.hidden = true;

    if (!resp.ok || !data.ok) {
      aiCampGenSetup.hidden = false;
      aiCampError.hidden = false;
      aiCampError.textContent = data.error || data.detail || "Eroare necunoscuta";
      return;
    }
    lastAiProposals = data.data.proposals;
    renderAiProposals(data);
  } catch (e) {
    aiCampLoading.hidden = true;
    aiCampGenSetup.hidden = false;
    aiCampError.hidden = false;
    aiCampError.textContent = "Eroare retea: " + e.message;
  }
}

function renderAiProposals(resp) {
  const d = resp.data;
  aiCampProposals.hidden = false;

  const cards = d.proposals.map((p, i) => {
    const channels = (p.channels || []).map((ch) => `<span class="pill">${CHANNEL_LABEL[ch] || ch}</span>`).join("");
    const taskList = (p.tasks || []).map((t) =>
      `<li>${escapeHtml(t.title)} <small style="color:var(--text-dim);">â€” ${escapeHtml(t.assignee)} (${t.priority}, ${t.deadline})</small></li>`
    ).join("");
    const productList = (p.products || []).map((pr) =>
      `<li>${escapeHtml(pr.name)} <small style="color:var(--text-dim);">â€” SKU ${escapeHtml(pr.sku)}${pr.qty_needed ? `, necesar ${pr.qty_needed}` : ""}</small></li>`
    ).join("");
    const dStr = formatDiscount(p.discount);
    const warns = p._warnings || [];
    const warnBlock = warns.length
      ? `<div class="ai-warn-box">âš  <strong>Atentie â€” produsele nu se potrivesc complet cu campania:</strong><ul style="margin:6px 0 0 18px;">${warns.map(w => `<li>${escapeHtml(w)}</li>`).join("")}</ul></div>`
      : "";

    return `
      <div class="ai-proposal-card${warns.length ? ' has-warnings' : ''}" data-idx="${i}">
        <div class="ai-proposal-head">
          <label class="ai-proposal-check">
            <input type="checkbox" data-prop-idx="${i}" checked />
            <span class="ai-proposal-title">${escapeHtml(p.name)}</span>
          </label>
          <span class="pill" style="background:rgba(79,140,255,0.15);color:var(--accent);">${TYPE_LABEL[p.type] || p.type}</span>
          <span class="pill" style="background:rgba(63,185,80,0.15);color:var(--success);">${(p.budget_alloc || 0).toFixed(0)} RON</span>
        </div>
        <div class="ai-proposal-meta">
          <span>ðŸ“… ${p.date_start} â†’ ${p.date_end}</span>
          <span>ðŸŽ¯ ${escapeHtml(p.mechanic)}</span>
          ${dStr ? `<span class="pill" style="background:rgba(63,185,80,0.15);color:var(--success);">ðŸ’° ${escapeHtml(dStr)}</span>` : ""}
          ${channels}
        </div>
        ${warnBlock}
        <div class="ai-proposal-body">
          <details>
            <summary><strong>ðŸ“¦ ${(p.products || []).length} produse</strong></summary>
            <ul style="margin:8px 0;padding-left:20px;">${productList}</ul>
          </details>
          <details>
            <summary><strong>ðŸ“‹ ${(p.tasks || []).length} task-uri sugerate</strong></summary>
            <ul style="margin:8px 0;padding-left:20px;">${taskList}</ul>
          </details>
          ${p.strategy_rationale ? `<div class="ai-rationale"><strong>ðŸ’¡ Rationale:</strong> ${escapeHtml(p.strategy_rationale)}</div>` : ""}
          ${p.notes ? `<div class="ai-notes"><strong>Note:</strong> ${escapeHtml(p.notes)}</div>` : ""}
        </div>
      </div>
    `;
  }).join("");

  aiCampProposals.innerHTML = `
    ${d.summary ? `<div class="ai-summary-box"><strong>Strategie globala:</strong> ${escapeHtml(d.summary)}</div>` : ""}
    <div class="ai-proposals-list">${cards}</div>
    <div class="form-actions" style="margin-top:20px;">
      <button type="button" class="btn" id="btnAiCampRetry">ðŸ”„ Genereaza altele</button>
      <span style="flex:1;"></span>
      <button type="button" class="btn btn-success" id="btnAiCampSave">ðŸ’¾ Salveaza cele bifate</button>
    </div>
  `;

  document.getElementById("btnAiCampRetry").addEventListener("click", () => {
    aiCampProposals.hidden = true;
    aiCampGenSetup.hidden = false;
  });
  document.getElementById("btnAiCampSave").addEventListener("click", saveAiProposals);
}

async function saveAiProposals() {
  const checked = Array.from(document.querySelectorAll('input[data-prop-idx]:checked'));
  if (!checked.length) {
    alert("Bifeaza cel putin o propunere.");
    return;
  }
  const selected = checked.map((cb) => lastAiProposals[Number(cb.dataset.propIdx)]);
  const btn = document.getElementById("btnAiCampSave");
  btn.disabled = true;
  btn.textContent = "Salvez...";
  try {
    const resp = await fetch("/api/campanii/ai-save-selected", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposals: selected }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      alert("Eroare: " + (data.detail || "necunoscuta"));
      btn.disabled = false;
      btn.textContent = "ðŸ’¾ Salveaza cele bifate";
      return;
    }
    aiCampGenModal.hidden = true;
    await loadCampaigns();
    alert(`âœ“ ${data.count} campanii salvate ca DRAFT in Hub.`);
  } catch (e) {
    alert("Eroare retea: " + e.message);
    btn.disabled = false;
    btn.textContent = "ðŸ’¾ Salveaza cele bifate";
  }
}

async function exportSedinta() {
  const orig = btnExportSedinta.textContent;
  btnExportSedinta.disabled = true;
  btnExportSedinta.textContent = "ðŸ“¦ Generez (~10s)...";
  try {
    const resp = await fetch("/api/exports/sedinta", { method: "POST" });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      alert("Eroare la export: " + (err.detail || resp.statusText));
      return;
    }
    const blob = await resp.blob();
    const cd = resp.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename="([^"]+)"/);
    const fname = match ? match[1] : "Export-Sedinta.zip";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 300);
    btnExportSedinta.textContent = "âœ“ Descarcat!";
    setTimeout(() => { btnExportSedinta.textContent = orig; }, 2000);
  } catch (e) {
    alert("Eroare retea: " + e.message);
    btnExportSedinta.textContent = orig;
  } finally {
    btnExportSedinta.disabled = false;
  }
}
modalClose.addEventListener("click", closeModal);
formCancel.addEventListener("click", closeModal);
modalEl.addEventListener("click", (e) => { if (e.target === modalEl) closeModal(); });

// Discount type â†’ enable/disable value input + show hint
const discountTypeEl  = document.getElementById("discountType");
const discountValueEl = document.getElementById("discountValue");
const discountHintEl  = document.getElementById("discountHint");
const DISCOUNT_HINTS = {
  none:        "",
  percent_off: "Ex: 10 = -10%",
  fixed_off:   "Ex: 5 = -5 RON din pret",
  fixed_price: "Pret final exact (RON)",
};
discountTypeEl.addEventListener("change", updateDiscountUi);
function updateDiscountUi() {
  const t = discountTypeEl.value;
  discountValueEl.disabled = (t === "none");
  if (t === "none") discountValueEl.value = "";
  discountHintEl.textContent = DISCOUNT_HINTS[t] || "";
}

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  await saveCampaign();
});

productSearchEl.addEventListener("input", onProductSearch);
productSearchEl.addEventListener("focus", onProductSearch);
document.addEventListener("click", (e) => {
  if (!productSearchEl.contains(e.target) && !productSearchResults.contains(e.target)) {
    productSearchResults.hidden = true;
  }
});

async function loadCampaigns() {
  await Promise.all([loadSnapshotInfo(), loadPricesInfo()]);
  try {
    const resp = await fetch("/api/campanii");
    const list = await resp.json();
    renderCampaignList(list);
  } catch (e) {
    campaignListEl.innerHTML = `<div class="placeholder">Eroare la incarcare: ${escapeHtml(e.message)}</div>`;
  }
}

const pricesBarEl = document.getElementById("pricesBar");
const pricesUploadEl = document.getElementById("pricesUpload");

async function loadPricesInfo() {
  try {
    const resp = await fetch("/api/preturi/snapshot");
    const data = await resp.json();
    if (data.available) {
      const d = new Date(data.uploaded_at);
      const dateStr = d.toLocaleDateString("ro-RO") + " " + d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" });
      pricesBarEl.classList.remove("empty");
      pricesBarEl.innerHTML = `ðŸ’° Lista preturi: <strong>${dateStr}</strong> &nbsp;â€¢&nbsp; <strong>${data.product_count}</strong> produse din <strong>${data.sheets.length}</strong> brand-uri (${escapeHtml(data.sheets.join(", "))}) <button class="btn btn-link" id="btnReuploadPrices">âŸ³ Reincarca</button>`;
    } else {
      pricesBarEl.classList.add("empty");
      pricesBarEl.innerHTML = `âš  Nu exista lista de preturi salvata. <button class="btn btn-link" id="btnUploadPrices">ðŸ“¤ Incarca PRETURI PRODUSE TOATE.xlsx</button>`;
    }
    document.getElementById("btnUploadPrices")?.addEventListener("click", () => pricesUploadEl.click());
    document.getElementById("btnReuploadPrices")?.addEventListener("click", () => pricesUploadEl.click());
  } catch {
    pricesBarEl.classList.add("empty");
    pricesBarEl.innerHTML = "âš  Nu pot verifica statusul listei de preturi.";
  }
}

pricesUploadEl.addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  pricesBarEl.innerHTML = "ðŸ“¤ Incarc lista de preturi...";
  try {
    const resp = await fetch("/api/preturi/upload", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      alert("Eroare: " + (data.detail || "necunoscuta"));
    } else {
      alert(`Gata! Am incarcat ${data.products_loaded} produse din ${data.sheets_processed.length} sheet-uri.`);
    }
  } catch (err) {
    alert("Eroare retea: " + err.message);
  }
  e.target.value = "";
  await loadPricesInfo();
});

async function loadSnapshotInfo() {
  try {
    const resp = await fetch("/api/stocuri/snapshot");
    snapshotData = await resp.json();
  } catch {
    snapshotData = { available: false };
  }
  if (snapshotData.available) {
    const d = new Date(snapshotData.uploaded_at);
    const dateStr = d.toLocaleDateString("ro-RO") + " " + d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" });
    snapshotBarEl.classList.remove("empty");
    snapshotBarEl.innerHTML = `ðŸ“¦ Stoc actualizat: <strong>${dateStr}</strong> &nbsp;â€¢&nbsp; sursa: <strong>${escapeHtml(snapshotData.source_filename || "â€”")}</strong> &nbsp;â€¢&nbsp; <strong>${snapshotData.rows.length}</strong> SKU-uri disponibile pentru validari`;
  } else {
    snapshotBarEl.classList.add("empty");
    snapshotBarEl.innerHTML = `âš  Nu exista raport de stocuri salvat. Mergi la <strong>Stocuri â†’ eMAG</strong> sau <strong>Shopify</strong> si ruleaza o sincronizare ca sa poti valida fezabilitatea campaniilor.`;
  }
}

function renderCampaignList(campaigns) {
  if (!campaigns.length) {
    campaignListEl.innerHTML = "";
    campaignEmptyEl.hidden = false;
    return;
  }
  campaignEmptyEl.hidden = true;
  // sort by date_start asc
  campaigns.sort((a, b) => (a.date_start || "").localeCompare(b.date_start || ""));
  campaignListEl.innerHTML = campaigns.map(renderCampaignCard).join("");
  campaignListEl.querySelectorAll(".btn-edit").forEach((b) => b.addEventListener("click", () => openModal(campaigns.find((c) => c.id === b.dataset.id))));
  campaignListEl.querySelectorAll(".btn-delete").forEach((b) => b.addEventListener("click", () => deleteCampaign(b.dataset.id, campaigns.find((c) => c.id === b.dataset.id)?.name)));
  campaignListEl.querySelectorAll(".btn-validate").forEach((b) => b.addEventListener("click", () => validateCampaign(b.dataset.id)));
  campaignListEl.querySelectorAll(".btn-prices").forEach((b) => b.addEventListener("click", () => calcPrices(b.dataset.id)));
  campaignListEl.querySelectorAll(".btn-reach").forEach((b) => b.addEventListener("click", () => estimateReach(b.dataset.id)));
  campaignListEl.querySelectorAll(".btn-ai").forEach((b) => b.addEventListener("click", () => openAiModal(b.dataset.id, campaigns.find((c) => c.id === b.dataset.id)?.name)));
  bindTaskHandlers(campaigns);
}

function renderCampaignCard(c) {
  const salesChannels = (c.channels || []).filter((ch) => ch === "shopify" || ch === "emag");
  const postChannels  = (c.channels || []).filter((ch) => ch === "instagram" || ch === "facebook");
  const channelsHtml = [
    salesChannels.length ? `<span class="pill">ðŸ›’ ${salesChannels.map((ch) => CHANNEL_LABEL[ch]).join(" + ")}</span>` : "",
    postChannels.length  ? `<span class="pill">ðŸ“£ ${postChannels.map((ch) => CHANNEL_LABEL[ch]).join(" + ")}</span>` : "",
  ].filter(Boolean).join("");

  const dateRange = formatDateRange(c.date_start, c.date_end);
  const budgetInfo = c.budget_alloc != null ? `<span>Buget: <strong>${formatMoney(c.budget_alloc)}</strong>${c.budget_spent != null ? ` / ${formatMoney(c.budget_spent)}` : ""}</span>` : "";
  const discountInfo = formatDiscount(c.discount);
  return `
    <div class="campaign-card" data-id="${c.id}">
      <div class="campaign-card-head">
        <div>
          <div class="campaign-title">
            ${escapeHtml(c.name)}
            <span class="status-badge status-${c.status}">${STATUS_LABEL[c.status] || c.status}</span>
          </div>
          <div class="campaign-meta">
            <span>ðŸ“… ${dateRange}</span>
            <span class="pill">${TYPE_LABEL[c.type] || c.type}</span>
            ${c.mechanic ? `<span>ðŸŽ¯ ${escapeHtml(c.mechanic)}</span>` : ""}
            ${discountInfo ? `<span class="pill" style="background:rgba(63,185,80,0.15);color:var(--success);">ðŸ’° ${escapeHtml(discountInfo)}</span>` : ""}
            <span>ðŸ“¦ ${(c.products || []).length} produse</span>
            ${budgetInfo}
            ${channelsHtml}
          </div>
        </div>
        <div class="campaign-actions">
          <button class="btn btn-validate" data-id="${c.id}">ðŸ” Valideaza stoc</button>
          <button class="btn btn-prices" data-id="${c.id}">ðŸ’° Calc preturi</button>
          <button class="btn btn-reach" data-id="${c.id}">ðŸ“Š Estimare reach</button>
          <button class="btn btn-ai" data-id="${c.id}" style="background:linear-gradient(135deg,var(--accent),#7c5cff);border-color:transparent;color:white;">ðŸ¤– AI continut</button>
          <button class="btn btn-edit" data-id="${c.id}">âœŽ Editeaza</button>
          <button class="btn btn-delete" data-id="${c.id}">ðŸ—‘ Sterge</button>
        </div>
      </div>
      ${c.notes ? `<div style="margin-top:10px;font-size:13px;color:var(--text-muted);white-space:pre-wrap;">${escapeHtml(c.notes)}</div>` : ""}
      ${renderTasksSection(c)}
      <div class="campaign-validation" data-validation="${c.id}" hidden></div>
      <div class="campaign-validation" data-prices="${c.id}" hidden></div>
      <div class="campaign-validation" data-reach="${c.id}" hidden></div>
    </div>
  `;
}

function formatDateRange(start, end) {
  if (!start && !end) return "â€”";
  const s = start ? new Date(start).toLocaleDateString("ro-RO") : "?";
  const e = end ? new Date(end).toLocaleDateString("ro-RO") : "?";
  return `${s} â†’ ${e}`;
}
function formatMoney(v) {
  return Number(v).toLocaleString("ro-RO", { style: "currency", currency: "RON", maximumFractionDigits: 0 });
}
function formatDiscount(d) {
  if (!d || d.type === "none" || d.value == null) return "";
  if (d.type === "percent_off") return `-${d.value}%`;
  if (d.type === "fixed_off")   return `-${d.value} RON`;
  if (d.type === "fixed_price") return `${d.value} RON pret nou`;
  return "";
}

function openModal(campaign = null) {
  editingCampaignId = campaign?.id || null;
  modalTitle.textContent = campaign ? `Editeaza: ${campaign.name}` : "Campanie noua";
  formEl.reset();
  formProducts = [];
  if (campaign) {
    formEl.name.value = campaign.name || "";
    formEl.type.value = campaign.type || "promo";
    formEl.status.value = campaign.status || "draft";
    formEl.mechanic.value = campaign.mechanic || "";
    formEl.date_start.value = campaign.date_start || "";
    formEl.date_end.value = campaign.date_end || "";
    formEl.budget_alloc.value = campaign.budget_alloc ?? "";
    formEl.budget_spent.value = campaign.budget_spent ?? "";
    formEl.notes.value = campaign.notes || "";
    formEl.querySelectorAll('input[name="channels"]').forEach((cb) => {
      cb.checked = (campaign.channels || []).includes(cb.value);
    });
    const d = campaign.discount || { type: "none", value: null };
    discountTypeEl.value = d.type || "none";
    discountValueEl.value = d.value ?? "";
    formProducts = (campaign.products || []).map((p) => ({ ...p }));
  } else {
    discountTypeEl.value = "none";
    discountValueEl.value = "";
  }
  updateDiscountUi();
  renderFormProducts();
  modalEl.hidden = false;
}

function closeModal() {
  modalEl.hidden = true;
  productSearchResults.hidden = true;
}

function onProductSearch() {
  const q = (productSearchEl.value || "").trim().toLowerCase();
  if (!snapshotData?.available || !q || q.length < 2) {
    productSearchResults.hidden = true;
    return;
  }
  const rows = snapshotData.rows.filter((r) => {
    return (r.sku || "").toLowerCase().includes(q)
        || (r.codmare || "").toLowerCase().includes(q)
        || (r.ean || "").toLowerCase().includes(q);
  }).slice(0, 12);
  if (!rows.length) {
    productSearchResults.innerHTML = `<div class="search-result" style="cursor:default;color:var(--text-dim);">Nimic gasit</div>`;
    productSearchResults.hidden = false;
    return;
  }
  productSearchResults.innerHTML = rows.map((r) => `
    <div class="search-result" data-sku="${escapeHtml(r.sku)}" data-codmare="${escapeHtml(r.codmare || "")}">
      <strong>SKU ${escapeHtml(r.sku)}</strong> Â· stoc curent: ${r.qty}
      <div class="codes">codmare: ${escapeHtml(r.codmare || "â€”")} Â· EAN: ${escapeHtml(r.ean || "â€”")}</div>
    </div>
  `).join("");
  productSearchResults.hidden = false;
  productSearchResults.querySelectorAll(".search-result[data-sku]").forEach((el) => {
    el.addEventListener("click", () => {
      addProductToForm({
        sku: el.dataset.sku,
        codmare: el.dataset.codmare || null,
        name: "",
        qty_needed: null,
      });
      productSearchEl.value = "";
      productSearchResults.hidden = true;
    });
  });
}

function addProductToForm(p) {
  if (formProducts.some((x) => x.sku === p.sku)) return; // duplicate
  formProducts.push(p);
  renderFormProducts();
}

function renderFormProducts() {
  campaignProductsEl.innerHTML = formProducts.map((p, i) => `
    <div class="product-row" data-i="${i}">
      <div class="pname">
        <strong>SKU ${escapeHtml(p.sku)}</strong>
        <small>${p.codmare ? "codmare " + escapeHtml(p.codmare) : "fara codmare"}</small>
      </div>
      <input type="number" min="0" class="qty" placeholder="qty necesar" value="${p.qty_needed ?? ""}" data-i="${i}" />
      <button type="button" class="remove" data-i="${i}" title="Elimina">Ã—</button>
    </div>
  `).join("");
  campaignProductsEl.querySelectorAll(".remove").forEach((b) => b.addEventListener("click", () => {
    formProducts.splice(Number(b.dataset.i), 1);
    renderFormProducts();
  }));
  campaignProductsEl.querySelectorAll("input.qty").forEach((inp) => inp.addEventListener("input", () => {
    const v = inp.value === "" ? null : Number(inp.value);
    formProducts[Number(inp.dataset.i)].qty_needed = v;
  }));
}

async function saveCampaign() {
  const fd = new FormData(formEl);
  const channels = Array.from(formEl.querySelectorAll('input[name="channels"]:checked')).map((cb) => cb.value);
  const dt = discountTypeEl.value;
  const dv = discountValueEl.value;
  const payload = {
    id: editingCampaignId || crypto.randomUUID(),
    name: fd.get("name").trim(),
    type: fd.get("type"),
    status: fd.get("status"),
    mechanic: fd.get("mechanic").trim(),
    date_start: fd.get("date_start"),
    date_end: fd.get("date_end"),
    channels,
    discount: {
      type: dt,
      value: (dt !== "none" && dv !== "") ? Number(dv) : null,
    },
    products: formProducts,
    budget_alloc: fd.get("budget_alloc") ? Number(fd.get("budget_alloc")) : null,
    budget_spent: fd.get("budget_spent") ? Number(fd.get("budget_spent")) : null,
    notes: fd.get("notes").trim(),
  };

  const url = editingCampaignId ? `/api/campanii/${editingCampaignId}` : "/api/campanii";
  const method = editingCampaignId ? "PUT" : "POST";
  try {
    const resp = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      alert("Eroare la salvare: " + (err.detail || resp.statusText));
      return;
    }
    closeModal();
    await loadCampaigns();
  } catch (e) {
    alert("Eroare retea: " + e.message);
  }
}

async function deleteCampaign(id, name) {
  if (!confirm(`Sterg campania "${name || id}"?`)) return;
  try {
    const resp = await fetch(`/api/campanii/${id}`, { method: "DELETE" });
    if (!resp.ok) { alert("Eroare la stergere"); return; }
    await loadCampaigns();
  } catch (e) {
    alert("Eroare: " + e.message);
  }
}

async function validateCampaign(id) {
  const target = document.querySelector(`[data-validation="${id}"]`);
  if (!target) return;
  target.hidden = false;
  target.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Verific...</div>`;
  try {
    const resp = await fetch(`/api/campanii/${id}/validate-stock`, { method: "POST" });
    const data = await resp.json();
    if (!data.ok) {
      target.innerHTML = `<div class="validation-overall blocked">âš  ${escapeHtml(data.error)}</div>`;
      return;
    }
    target.innerHTML = renderValidation(data);
  } catch (e) {
    target.innerHTML = `<div class="validation-overall blocked">Eroare: ${escapeHtml(e.message)}</div>`;
  }
}

async function calcPrices(id) {
  const target = document.querySelector(`[data-prices="${id}"]`);
  if (!target) return;
  target.hidden = false;
  target.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Calculez preturi...</div>`;
  try {
    const resp = await fetch(`/api/campanii/${id}/calculate-prices`, { method: "POST" });
    const data = await resp.json();
    if (!data.ok) {
      target.innerHTML = `<div class="validation-overall blocked">âš  ${escapeHtml(data.error)}</div>`;
      return;
    }
    target.innerHTML = renderPrices(data, id);
    target.querySelector(".btn-download-prices")?.addEventListener("click", () => {
      const fname = `preturi-${slugify(data.campaign_name)}-${new Date().toISOString().slice(0, 10)}.xlsx`;
      triggerDownload(data.file_b64, fname);
    });
  } catch (e) {
    target.innerHTML = `<div class="validation-overall blocked">Eroare: ${escapeHtml(e.message)}</div>`;
  }
}

function slugify(s) {
  return String(s).toLowerCase().normalize("NFD").replace(/[Ì€-Í¯]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "campanie";
}

function renderPrices(d, cid) {
  const s = d.summary;
  const dapp = d.discount_applied;
  const dStr = dapp.type === "none" ? "fara reducere"
    : dapp.type === "percent_off" ? `-${dapp.value}% pe Pret V`
    : dapp.type === "fixed_off"   ? `-${dapp.value} RON pe Pret V`
    : dapp.type === "fixed_price" ? `Pret V nou: ${dapp.value} RON`
    : "â€”";

  const rows = d.lines.map((l) => {
    if (!l.found) {
      return `<tr><td>${escapeHtml(l.codmare || l.sku)}</td><td colspan="6" style="color:var(--text-dim);font-style:italic;">${escapeHtml(l.note)}</td></tr>`;
    }
    const noteCell = l.note ? `<span class="row-status-insufficient">${escapeHtml(l.note)}</span>` : "";
    return `
      <tr>
        <td>${escapeHtml(l.codmare || l.sku)}<br><small style="color:var(--text-dim)">${escapeHtml(l.brand || "")}</small></td>
        <td>${l.base_v != null ? l.base_v.toFixed(2) : "â€”"}</td>
        <td><strong style="color:var(--success)">${l.new_v != null ? l.new_v.toFixed(2) : "â€”"}</strong></td>
        <td>${l.new_min != null ? l.new_min.toFixed(2) : "â€”"}</td>
        <td>${l.new_max != null ? l.new_max.toFixed(2) : "â€”"}</td>
        <td>${noteCell}</td>
      </tr>
    `;
  }).join("");

  return `
    <div class="validation-overall ok">ðŸ’° Preturi calculate (${dStr})</div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
      ${s.matched} mapate Â· ${s.not_found} negasite Â· ${s.warnings_below_min} sub Pret Minim
    </div>
    <table class="validation-items">
      <thead><tr>
        <th>Produs</th>
        <th>Pret V (vechi)</th>
        <th>Pret V (NOU)</th>
        <th>Pret Minim</th>
        <th>Pret Maxim</th>
        <th>Note</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center;">
      <button class="btn btn-success btn-download-prices">â¬‡ Descarca Excel (eMAG + Shopify)</button>
      <span style="font-size:11px;color:var(--text-dim);">Excel-ul are 2 sheet-uri: 'eMAG' (3 preturi) si 'Shopify' (1 pret)</span>
    </div>
  `;
}

async function estimateReach(id) {
  const target = document.querySelector(`[data-reach="${id}"]`);
  if (!target) return;
  target.hidden = false;
  target.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Estimez reach...</div>`;
  try {
    const resp = await fetch(`/api/campanii/${id}/estimate-reach`, { method: "POST" });
    const data = await resp.json();
    if (!data.ok) {
      target.innerHTML = `<div class="validation-overall blocked">âš  ${escapeHtml(data.error)}</div>`;
      return;
    }
    target.innerHTML = renderReach(data);
  } catch (e) {
    target.innerHTML = `<div class="validation-overall blocked">Eroare: ${escapeHtml(e.message)}</div>`;
  }
}

function renderReach(d) {
  const rows = d.breakdown.map((b) => `
    <tr>
      <td>${CHANNEL_LABEL[b.channel] || b.channel}</td>
      <td>${formatMoney(b.budget)}</td>
      <td>${b.cpm.toFixed(2)} RON</td>
      <td><strong>${b.estimated_impressions.toLocaleString("ro-RO")}</strong></td>
      <td>${b.estimated_engaged.toLocaleString("ro-RO")}</td>
    </tr>
  `).join("");
  return `
    <div class="validation-overall ok">ðŸ“Š Estimare reach pentru ${formatMoney(d.total_budget)}</div>
    <table class="validation-items">
      <thead><tr>
        <th>Canal</th><th>Buget</th><th>CPM</th>
        <th>Impresii estimate</th><th>Engagement (~${(d.engagement_rate_assumed*100).toFixed(1)}%)</th>
      </tr></thead>
      <tbody>${rows}</tbody>
      <tfoot>
        <tr style="font-weight:600;">
          <td colspan="3" style="text-align:right;">Total:</td>
          <td>${d.total_estimated_impressions.toLocaleString("ro-RO")}</td>
          <td>${d.total_estimated_engaged.toLocaleString("ro-RO")}</td>
        </tr>
      </tfoot>
    </table>
    <div style="margin-top:8px;font-size:11px;color:var(--text-dim);line-height:1.5;">${escapeHtml(d.note)}</div>
  `;
}

function renderValidation(d) {
  const overallText = {
    ok:      "âœ“ Stoc suficient pentru toate produsele",
    warning: "âš  Verifica produsele cu probleme",
    blocked: "âœ— Stoc insuficient â€” campania ar putea avea probleme",
  }[d.overall] || d.overall;
  const statusLabels = {
    sufficient:  "âœ“ Suficient",
    tight:       "âš  Strans",
    insufficient: "âœ— Insuficient",
    info:        "â€”",
    not_found:   "â“ Negasit in raport",
  };
  const rows = d.items.map((it) => {
    const codeCell = `${escapeHtml(it.sku)}${it.codmare ? ` <small style="color:var(--text-dim)">(${escapeHtml(it.codmare)})</small>` : ""}`;
    const stockCell = it.stock_available === null
      ? `<span style="color:var(--text-dim);font-style:italic;">â€”</span>`
      : it.stock_available;
    const coverageCell = it.coverage != null ? Math.round(it.coverage * 100) + "%" : "â€”";
    const matchedHint = it.matched_via && it.status !== "not_found"
      ? ` <small style="color:var(--text-dim);font-weight:normal;">(via ${it.matched_via})</small>` : "";
    return `<tr>
      <td>${codeCell}</td>
      <td>${it.qty_needed ?? "â€”"}</td>
      <td>${stockCell}</td>
      <td>${coverageCell}</td>
      <td class="row-status-${it.status}">${statusLabels[it.status] || it.status}${matchedHint}</td>
    </tr>`;
  }).join("");
  const snapDate = new Date(d.snapshot_uploaded_at).toLocaleString("ro-RO", { dateStyle: "short", timeStyle: "short" });
  return `
    <div class="validation-overall ${d.overall}">${overallText}</div>
    <table class="validation-items">
      <thead><tr><th>Produs (SKU)</th><th>Necesar</th><th>Stoc</th><th>Acoperire</th><th>Status</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="margin-top:8px;font-size:11px;color:var(--text-dim);">Bazat pe raportul din ${snapDate}</div>
  `;
}


