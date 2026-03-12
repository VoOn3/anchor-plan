const API_BASE = "http://localhost:5000/api";

const params = new URLSearchParams(window.location.search);
const projectId = params.get("id");

if (!projectId) {
    window.location.href = "index.html";
}

let state = {
    projectId: projectId,
    analysis: [],
    plan: [],
    settings: null,
    selectedUrls: new Set(),
    editingRowIndex: null,
    projectName: "",
    collabColumns: [],
    collabCount: 0,
};

const REC_LABELS = {
    priority: "Пріоритетно",
    recommended: "Рекомендовано",
    needs_support: "Потребує підтримки",
    has_potential: "Має потенціал",
    observe: "Спостерігати",
    not_recommended: "Не рекомендовано",
};

loadProject();

async function loadProject() {
    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}`);
        if (!resp.ok) {
            alert("Проект не знайдено");
            window.location.href = "index.html";
            return;
        }
        const data = await resp.json();

        state.projectName = data.name;
        state.analysis = data.analysis || [];
        state.plan = data.plan || [];
        state.settings = data.settings || null;
        state.selectedUrls = new Set(data.selected_urls || []);

        document.title = `${data.name} — Anchor Plan`;
        const logoSpan = document.querySelector(".sidebar-logo span");
        if (logoSpan) logoSpan.textContent = data.name;

        if (data.brand_name) {
            document.getElementById("brand-name").value = data.brand_name;
        }

        if (state.analysis.length > 0) {
            enableNav();
            renderDashboard();
            renderPlan();
            if (state.settings) renderSettings();
        } else if (state.settings) {
            renderSettings();
        }

        loadCollabColumns();
    } catch (err) {
        console.error("Failed to load project:", err);
    }
}

async function loadCollabColumns() {
    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/collaborator-columns`);
        if (!resp.ok) return;
        const data = await resp.json();
        state.collabCount = data.count;
        state.collabColumns = data.columns;
        if (data.count > 0) {
            document.getElementById("collab-status").textContent = `${data.count} площадок завантажено`;
            document.getElementById("collab-status").className = "collab-status success";
            document.getElementById("site-filters-section").style.display = "block";
            renderExistingFilters();
        }
    } catch (e) { /* ignore */ }
}

// --- Navigation ---
document.querySelectorAll(".sidebar-menu li[data-section]").forEach((item) => {
    item.addEventListener("click", () => {
        if (item.classList.contains("disabled")) return;
        if (item.dataset.section === "projects-link") return;
        switchSection(item.dataset.section);
    });
});

function switchSection(sectionName) {
    document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
    document.getElementById(`${sectionName}-section`).classList.add("active");
    document.querySelectorAll(".sidebar-menu li").forEach((li) => li.classList.remove("active"));
    const target = document.querySelector(`.sidebar-menu li[data-section="${sectionName}"]`);
    if (target) target.classList.add("active");
}

function enableNav() {
    document.querySelectorAll(".sidebar-menu li.disabled").forEach((li) => li.classList.remove("disabled"));
}

// --- File Upload ---
document.querySelectorAll(".upload-dropzone").forEach((zone) => {
    const inputId = zone.dataset.input;
    const input = document.getElementById(inputId);
    const btn = zone.querySelector(".btn");

    btn.addEventListener("click", (e) => { e.stopPropagation(); input.click(); });
    zone.addEventListener("click", () => input.click());
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        if (e.dataTransfer.files.length) {
            input.files = e.dataTransfer.files;
            input.dispatchEvent(new Event("change"));
        }
    });
    input.addEventListener("change", () => {
        if (input.files.length) {
            const file = input.files[0];
            zone.classList.add("has-file");
            zone.closest(".upload-card").querySelector(".upload-status").innerHTML =
                `<i class="fas fa-check-circle"></i> ${file.name} (${formatSize(file.size)})`;
            checkCanAnalyze();
        }
    });
});

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
}

function checkCanAnalyze() {
    const ok = document.getElementById("positions-file").files.length > 0 &&
               document.getElementById("ahrefs-file").files.length > 0;
    document.getElementById("analyze-btn").disabled = !ok;
}

// --- Analyze ---
document.getElementById("analyze-btn").addEventListener("click", async () => {
    const formData = new FormData();
    formData.append("positions", document.getElementById("positions-file").files[0]);
    formData.append("ahrefs", document.getElementById("ahrefs-file").files[0]);
    formData.append("brand_name", document.getElementById("brand-name").value.trim());

    const loader = document.getElementById("loader");
    const btn = document.getElementById("analyze-btn");
    btn.disabled = true;
    loader.style.display = "flex";

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/upload`, { method: "POST", body: formData });
        const data = await resp.json();
        if (!resp.ok) { alert(data.error || "Помилка"); return; }

        state.analysis = data.analysis;
        state.plan = data.plan;
        state.settings = data.settings;
        state.selectedUrls = new Set(data.selected_urls || []);

        enableNav();
        renderDashboard();
        renderPlan();
        renderSettings();
        switchSection("dashboard");
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
        loader.style.display = "none";
    }
});

// --- Dashboard ---
function renderDashboard() {
    const a = state.analysis;
    const highCount = a.filter((p) => p.priority === "high").length;
    const medCount = a.filter((p) => p.priority === "medium").length;
    const lowCount = a.filter((p) => p.priority === "low").length;

    document.getElementById("stats-row").innerHTML = `
        <div class="stat-card total"><div class="stat-value">${a.length}</div><div class="stat-label">Всього сторінок</div></div>
        <div class="stat-card high"><div class="stat-value">${highCount}</div><div class="stat-label">Високий пріоритет</div></div>
        <div class="stat-card medium"><div class="stat-value">${medCount}</div><div class="stat-label">Середній пріоритет</div></div>
        <div class="stat-card low"><div class="stat-value">${lowCount}</div><div class="stat-label">Низький пріоритет</div></div>
    `;

    renderDashboardTable(a);
    updateSelectionBar();
}

function renderDashboardTable(data) {
    const tbody = document.querySelector("#dashboard-table tbody");
    tbody.innerHTML = data.map((page) => {
        const checked = state.selectedUrls.has(page.url) ? "checked" : "";
        const rowCls = checked ? "row-selected" : "";
        const rec = page.recommendation || "not_recommended";
        return `
        <tr class="${rowCls}">
            <td><input type="checkbox" class="url-cb" data-url="${page.url}" ${checked}></td>
            <td class="url-cell"><a href="detail.html?project=${encodeURIComponent(projectId)}&url=${encodeURIComponent(page.url)}" title="${page.url}">${shortenUrl(page.url)}</a></td>
            <td><span class="badge badge-${rec}">${REC_LABELS[rec] || rec}</span></td>
            <td><span class="badge badge-${page.priority}">${page.priority.toUpperCase()}</span></td>
            <td>${page.best_keyword ? page.best_keyword.keyword : "—"}</td>
            <td>${page.best_keyword?.current_position ?? "—"}</td>
            <td class="dynamics-${page.best_keyword?.dynamics_label || "stable"}">${getDynamicsIcon(page.best_keyword?.dynamics_label)} ${page.best_keyword?.dynamics_label || "—"}</td>
            <td>${page.total_backlinks}</td>
            <td>${page.dofollow_count}</td>
            <td>${page.anchor_profile.unique_anchors}</td>
        </tr>`;
    }).join("");

    tbody.querySelectorAll(".url-cb").forEach((cb) => {
        cb.addEventListener("change", () => {
            if (cb.checked) state.selectedUrls.add(cb.dataset.url);
            else state.selectedUrls.delete(cb.dataset.url);
            cb.closest("tr").classList.toggle("row-selected", cb.checked);
            updateSelectionBar();
        });
    });

    document.getElementById("select-all-cb").checked =
        data.length > 0 && data.every((p) => state.selectedUrls.has(p.url));
}

function updateSelectionBar() {
    const bar = document.getElementById("selection-bar");
    const total = state.analysis.length;
    const selected = state.selectedUrls.size;
    document.getElementById("selection-count").textContent = `Обрано: ${selected} з ${total}`;
    bar.style.display = total > 0 ? "flex" : "none";
}

// Select All checkbox
document.getElementById("select-all-cb").addEventListener("change", (e) => {
    const checked = e.target.checked;
    document.querySelectorAll(".url-cb").forEach((cb) => {
        cb.checked = checked;
        if (checked) state.selectedUrls.add(cb.dataset.url);
        else state.selectedUrls.delete(cb.dataset.url);
        cb.closest("tr").classList.toggle("row-selected", checked);
    });
    updateSelectionBar();
});

// Quick selection buttons
document.getElementById("btn-accept-recommended").addEventListener("click", () => {
    state.selectedUrls.clear();
    state.analysis.forEach((p) => {
        if (p.recommendation === "priority" || p.recommendation === "recommended")
            state.selectedUrls.add(p.url);
    });
    rerenderCheckboxes();
});

document.getElementById("btn-include-potential").addEventListener("click", () => {
    state.analysis.forEach((p) => {
        if (p.recommendation === "has_potential" || p.recommendation === "needs_support")
            state.selectedUrls.add(p.url);
    });
    rerenderCheckboxes();
});

document.getElementById("btn-select-all").addEventListener("click", () => {
    state.analysis.forEach((p) => state.selectedUrls.add(p.url));
    rerenderCheckboxes();
});

document.getElementById("btn-select-none").addEventListener("click", () => {
    state.selectedUrls.clear();
    rerenderCheckboxes();
});

function rerenderCheckboxes() {
    document.querySelectorAll(".url-cb").forEach((cb) => {
        cb.checked = state.selectedUrls.has(cb.dataset.url);
        cb.closest("tr").classList.toggle("row-selected", cb.checked);
    });
    document.getElementById("select-all-cb").checked =
        state.analysis.length > 0 && state.analysis.every((p) => state.selectedUrls.has(p.url));
    updateSelectionBar();
}

// Generate plan button
document.getElementById("btn-generate-plan").addEventListener("click", async () => {
    const btn = document.getElementById("btn-generate-plan");
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Генеруємо...';

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/select-urls`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ selected_urls: [...state.selectedUrls] }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.plan = data.plan;
            renderPlan();
            switchSection("plan");
        }
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic"></i> Сформувати анкор-план';
    }
});

// Dashboard filters
document.getElementById("dashboard-search").addEventListener("input", filterDashboard);
document.getElementById("priority-filter").addEventListener("change", filterDashboard);
document.getElementById("recommendation-filter").addEventListener("change", filterDashboard);

function filterDashboard() {
    const search = document.getElementById("dashboard-search").value.toLowerCase();
    const priority = document.getElementById("priority-filter").value;
    const rec = document.getElementById("recommendation-filter").value;

    let filtered = state.analysis;
    if (search) filtered = filtered.filter((p) =>
        p.url.toLowerCase().includes(search) || p.keywords.some((k) => k.keyword.toLowerCase().includes(search)));
    if (priority) filtered = filtered.filter((p) => p.priority === priority);
    if (rec) filtered = filtered.filter((p) => p.recommendation === rec);
    renderDashboardTable(filtered);
}

// --- Plan ---
function renderPlan() { renderPlanTable(state.plan); }

function renderPlanTable(data) {
    const tbody = document.querySelector("#plan-table tbody");
    tbody.innerHTML = data.map((item, idx) => {
        const order = item.purchase_order || 6;
        return `
        <tr class="${item.is_manual ? "manual-edit" : ""}">
            <td><span class="order-badge order-${order}">${order}</span></td>
            <td class="url-cell"><a href="detail.html?project=${encodeURIComponent(projectId)}&url=${encodeURIComponent(item.url)}" title="${item.url}">${shortenUrl(item.url)}</a></td>
            <td class="editable-cell" data-row="${idx}">${item.recommended_anchor}</td>
            <td><span class="badge badge-${item.anchor_type}">${formatAnchorType(item.anchor_type)}</span></td>
            <td>${item.target_keyword || "—"}</td>
            <td>${item.current_position ?? "—"}</td>
            <td class="dynamics-${item.dynamics}">${getDynamicsIcon(item.dynamics)} ${item.dynamics}</td>
            <td class="rationale-text">${item.rationale || item.comment || ""}</td>
            <td><button class="btn-icon edit-row-btn" data-row="${idx}" title="Редагувати"><i class="fas fa-pen"></i></button></td>
        </tr>`;
    }).join("");

    tbody.querySelectorAll(".edit-row-btn").forEach((btn) =>
        btn.addEventListener("click", () => openEditModal(parseInt(btn.dataset.row))));
    tbody.querySelectorAll(".editable-cell").forEach((cell) =>
        cell.addEventListener("dblclick", () => openEditModal(parseInt(cell.dataset.row))));
}

// Plan filters
document.getElementById("plan-search").addEventListener("input", filterPlan);
document.getElementById("plan-priority-filter").addEventListener("change", filterPlan);
document.getElementById("plan-type-filter").addEventListener("change", filterPlan);

function filterPlan() {
    const search = document.getElementById("plan-search").value.toLowerCase();
    const priority = document.getElementById("plan-priority-filter").value;
    const type = document.getElementById("plan-type-filter").value;
    let filtered = state.plan;
    if (search) filtered = filtered.filter((p) =>
        p.url.toLowerCase().includes(search) || p.recommended_anchor.toLowerCase().includes(search) ||
        (p.target_keyword && p.target_keyword.toLowerCase().includes(search)));
    if (priority) filtered = filtered.filter((p) => p.priority === priority);
    if (type) filtered = filtered.filter((p) => p.anchor_type === type);
    renderPlanTable(filtered);
}

// --- Edit Modal ---
function openEditModal(rowIndex) {
    state.editingRowIndex = rowIndex;
    const item = state.plan[rowIndex];
    document.getElementById("edit-anchor-text").value = item.recommended_anchor;
    document.getElementById("edit-anchor-type").value = item.anchor_type;
    document.getElementById("edit-modal").style.display = "flex";
}

document.getElementById("modal-close").addEventListener("click", closeModal);
document.getElementById("modal-cancel").addEventListener("click", closeModal);
document.getElementById("edit-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("edit-modal")) closeModal();
});

function closeModal() {
    document.getElementById("edit-modal").style.display = "none";
    state.editingRowIndex = null;
}

document.getElementById("modal-save").addEventListener("click", async () => {
    const anchor = document.getElementById("edit-anchor-text").value.trim();
    const anchorType = document.getElementById("edit-anchor-type").value;
    if (!anchor) return;

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/plan/edit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ row_index: state.editingRowIndex, anchor, anchor_type: anchorType }),
        });
        const data = await resp.json();
        if (resp.ok) { state.plan = data.plan; renderPlan(); }
    } catch (err) {
        state.plan[state.editingRowIndex].recommended_anchor = anchor;
        state.plan[state.editingRowIndex].anchor_type = anchorType;
        state.plan[state.editingRowIndex].is_manual = true;
        renderPlan();
    }
    closeModal();
});

// --- Settings ---
function renderSettings() {
    if (!state.settings) return;
    const dist = state.settings.anchor_distribution;
    const distContainer = document.getElementById("distribution-settings");
    const typeLabels = { exact_match: "Exact Match", partial_match: "Partial Match", branded: "Branded", generic: "Generic", url: "URL / Naked Link" };

    distContainer.innerHTML = Object.entries(dist).map(([key, val]) => `
        <div class="field-row">
            <label>${typeLabels[key] || key}</label>
            <input type="number" data-dist="${key}" data-bound="min" value="${val.min}" min="0" max="100" style="width:60px">
            <span class="range-sep">—</span>
            <input type="number" data-dist="${key}" data-bound="max" value="${val.max}" min="0" max="100" style="width:60px">
            <span class="range-sep">%</span>
        </div>`).join("");

    const prioRanges = state.settings.priority_ranges;
    const prioContainer = document.getElementById("priority-settings");
    const prioLabels = { high: "Високий", medium: "Середній", low_top: "Низький (ТОП)", low_bottom: "Низький (дно)" };

    prioContainer.innerHTML = Object.entries(prioRanges).map(([key, val]) => `
        <div class="field-row">
            <label>${prioLabels[key] || key}</label>
            <input type="number" data-prio="${key}" data-bound="from" value="${val.from}" min="1" max="1000" style="width:60px">
            <span class="range-sep">—</span>
            <input type="number" data-prio="${key}" data-bound="to" value="${val.to}" min="1" max="1000" style="width:60px">
            <span class="range-sep">поз.</span>
        </div>`).join("");

    document.getElementById("settings-brand").value = state.settings.brand_name || "";
    document.getElementById("settings-links-per-page").value = state.settings.links_per_page || 3;
    document.getElementById("settings-budget").value = state.settings.monthly_budget || 0;
    document.getElementById("settings-planned-links").value = state.settings.planned_links_count || 0;
}

// --- Recalculate ---
document.getElementById("recalculate-btn").addEventListener("click", async () => {
    const newSettings = collectSettings();
    const btn = document.getElementById("recalculate-btn");
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Перераховуємо...';

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/recalculate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ settings: newSettings, selected_urls: [...state.selectedUrls] }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.plan = data.plan;
            state.settings = data.settings;
            renderPlan();
            switchSection("plan");
        } else { alert(data.error || "Помилка"); }
    } catch (err) { alert("Помилка: " + err.message); }
    finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync-alt"></i> Перерахувати план';
    }
});

function collectSettings() {
    const settings = {
        anchor_distribution: {}, priority_ranges: {},
        brand_name: document.getElementById("settings-brand").value.trim(),
        links_per_page: parseInt(document.getElementById("settings-links-per-page").value) || 3,
        monthly_budget: parseFloat(document.getElementById("settings-budget").value) || 0,
        planned_links_count: parseInt(document.getElementById("settings-planned-links").value) || 0,
        site_filters: collectFilters(),
    };
    document.querySelectorAll("[data-dist]").forEach((input) => {
        const key = input.dataset.dist, bound = input.dataset.bound;
        if (!settings.anchor_distribution[key]) settings.anchor_distribution[key] = {};
        settings.anchor_distribution[key][bound] = parseInt(input.value) || 0;
    });
    document.querySelectorAll("[data-prio]").forEach((input) => {
        const key = input.dataset.prio, bound = input.dataset.bound;
        if (!settings.priority_ranges[key]) settings.priority_ranges[key] = {};
        settings.priority_ranges[key][bound] = parseInt(input.value) || 1;
    });
    return settings;
}

// --- Export ---
document.getElementById("export-btn").addEventListener("click", () => {
    window.open(`${API_BASE}/projects/${projectId}/export`, "_blank");
});

// --- Helpers ---
function shortenUrl(url) {
    try { const u = new URL(url); return u.hostname + (u.pathname === "/" ? "" : u.pathname); }
    catch { return url; }
}
function getDynamicsIcon(label) {
    if (label === "growth") return '<i class="fas fa-arrow-up"></i>';
    if (label === "decline") return '<i class="fas fa-arrow-down"></i>';
    return '<i class="fas fa-minus"></i>';
}
function formatAnchorType(type) {
    return { exact_match: "Exact", partial_match: "Partial", branded: "Brand", generic: "Generic", url: "URL" }[type] || type;
}

// --- Collaborator Upload ---
document.getElementById("btn-upload-collab").addEventListener("click", () => {
    document.getElementById("collaborator-file").click();
});

document.getElementById("collaborator-file").addEventListener("change", async () => {
    const file = document.getElementById("collaborator-file").files[0];
    if (!file) return;

    const statusEl = document.getElementById("collab-status");
    statusEl.textContent = "Завантажуємо...";
    statusEl.className = "collab-status";

    const formData = new FormData();
    formData.append("collaborator", file);

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/upload-collaborator`, {
            method: "POST", body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) { statusEl.textContent = data.error || "Помилка"; return; }

        state.collabCount = data.count;
        state.collabColumns = data.columns;
        statusEl.textContent = `${data.count} площадок завантажено`;
        statusEl.className = "collab-status success";
        document.getElementById("site-filters-section").style.display = "block";
    } catch (err) {
        statusEl.textContent = "Помилка: " + err.message;
    }
});

// --- Dynamic Filters ---
const NUM_OPS = [
    { value: ">=", label: "≥" },
    { value: "<=", label: "≤" },
    { value: "=", label: "=" },
];
const TEXT_OPS = [
    { value: "=", label: "=" },
    { value: "contains", label: "∋ містить" },
    { value: "not_contains", label: "∌ не містить" },
];

function renderExistingFilters() {
    const existing = state.settings?.site_filters || [];
    const container = document.getElementById("filters-list");
    container.innerHTML = "";
    existing.forEach((f) => addFilterRow(f.field, f.op, f.value));
}

document.getElementById("btn-add-filter").addEventListener("click", () => addFilterRow());

function addFilterRow(fieldVal = "", opVal = "", valueVal = "") {
    const container = document.getElementById("filters-list");
    const row = document.createElement("div");
    row.className = "filter-row";

    const fieldSelect = document.createElement("select");
    fieldSelect.className = "field-select";
    fieldSelect.innerHTML = '<option value="">— Оберіть параметр —</option>' +
        state.collabColumns.map((c) =>
            `<option value="${c.name}" data-type="${c.type}" ${c.name === fieldVal ? "selected" : ""}>${c.name}</option>`
        ).join("");

    const opSelect = document.createElement("select");
    opSelect.className = "op-select";

    const valueInput = document.createElement("input");
    valueInput.className = "filter-value";
    valueInput.type = "text";
    valueInput.placeholder = "Значення";
    valueInput.value = valueVal;

    const removeBtn = document.createElement("button");
    removeBtn.className = "btn-remove-filter";
    removeBtn.innerHTML = "×";
    removeBtn.addEventListener("click", () => row.remove());

    function updateOps() {
        const opt = fieldSelect.selectedOptions[0];
        const type = opt?.dataset?.type || "text";
        const ops = type === "number" ? NUM_OPS : TEXT_OPS;
        opSelect.innerHTML = ops.map((o) =>
            `<option value="${o.value}" ${o.value === opVal ? "selected" : ""}>${o.label}</option>`
        ).join("");
    }

    fieldSelect.addEventListener("change", () => { opVal = ""; updateOps(); });
    updateOps();

    row.append(fieldSelect, opSelect, valueInput, removeBtn);
    container.appendChild(row);
}

function collectFilters() {
    const rows = document.querySelectorAll("#filters-list .filter-row");
    const filters = [];
    rows.forEach((row) => {
        const field = row.querySelector(".field-select")?.value;
        const op = row.querySelector(".op-select")?.value;
        const value = row.querySelector(".filter-value")?.value?.trim();
        if (field && op && value !== "") {
            const col = state.collabColumns.find((c) => c.name === field);
            const isNum = col?.type === "number";
            filters.push({ field, op, value: isNum ? parseFloat(value) || value : value });
        }
    });
    return filters;
}

// Apply filters
document.getElementById("btn-apply-filters").addEventListener("click", async () => {
    const filters = collectFilters();
    const btn = document.getElementById("btn-apply-filters");
    btn.disabled = true;

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/filter-sites`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filters }),
        });
        const data = await resp.json();
        if (!resp.ok) { alert(data.error || "Помилка"); return; }

        const resultsEl = document.getElementById("filter-results");
        const budget = parseFloat(document.getElementById("settings-budget").value) || 0;
        let html = `
            <span class="filter-stat">Всього: <strong>${data.total}</strong></span>
            <span class="filter-stat">Пройшло фільтр: <strong>${data.filtered}</strong></span>
            <span class="filter-stat">Орієнтовна вартість: <strong>${data.total_cost.toLocaleString()} UAH</strong></span>
        `;
        if (budget > 0) {
            html += `<span class="filter-stat">Вкладається в бюджет: <strong>${data.within_budget}</strong></span>`;
        }
        resultsEl.innerHTML = html;

        renderSitesTable(data.sites);
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
    }
});

function renderSitesTable(sites) {
    const wrap = document.getElementById("sites-table-wrap");
    if (!sites.length) { wrap.style.display = "none"; return; }
    wrap.style.display = "block";

    const showCols = ["Домен", "DR", "Трафік на місяць", "Органічний трафік", "Da Moz", "TF",
        "Вік сайту, років", "Тематика", "Країна", "Ціна розміщення стаття, UAH"];
    const available = showCols.filter((c) => sites[0].hasOwnProperty(c));

    document.getElementById("sites-thead-row").innerHTML =
        available.map((c) => `<th>${c}</th>`).join("");

    document.querySelector("#sites-table tbody").innerHTML =
        sites.slice(0, 100).map((s) => `<tr>${available.map((c) => {
            let v = s[c];
            if (v == null) v = "—";
            if (c === "Домен" && typeof v === "string" && v.startsWith("http")) {
                const short = v.replace(/^https?:\/\//, "").replace(/\/$/, "");
                return `<td><a href="${v}" target="_blank">${short}</a></td>`;
            }
            if (typeof v === "number") v = v.toLocaleString();
            return `<td>${v}</td>`;
        }).join("")}</tr>`).join("");
}
