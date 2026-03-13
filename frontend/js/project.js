const API_BASE = (typeof window !== "undefined" && window.location.port === "5000") ? "/api" : "http://localhost:5000/api";

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
    settingsHistory: [],
    settingsPresets: [],
    selectedUrls: new Set(),
    selectedPlanRows: new Set(),
    editingRowIndex: null,
    projectName: "",
    collabColumns: [],
    collabCount: 0,
    purchaseAssignments: [],
    purchaseStats: null,
    customLinks: {},
    dashboardSort: { column: "priority_score", direction: "desc" },
};

const REC_LABELS = {
    priority: "Пріоритетно",
    recommended: "Рекомендовано",
    needs_support: "Потребує підтримки",
    has_potential: "Має потенціал",
    observe: "Спостерігати",
    not_recommended: "Не рекомендовано",
};

const REC_ORDER = { priority: 1, recommended: 2, needs_support: 3, has_potential: 4, observe: 5, not_recommended: 6 };
const PRIORITY_ORDER = { high: 1, medium: 2, low: 3 };
const DYNAMICS_ORDER = { growth: 1, stable: 2, decline: 3 };

const REC_TOOLTIPS = {
    priority: "Пріоритетні сторінки з найкращими позиціями та позитивною динамікою. Рекомендовано для закупок.",
    recommended: "Сторінки з хорошим потенціалом. Рекомендовано включати в анкор-план.",
    needs_support: "Позиції падають або потребують підтримки. Потрібні закупки для стабілізації.",
    has_potential: "Сторінки з потенціалом для росту. Можна включати в план.",
    observe: "Сторінки для спостереження. Низький пріоритет закупок.",
    not_recommended: "Низький пріоритет або відсутність даних. Не рекомендовано для закупок.",
};
const PRIORITY_TOOLTIPS = {
    high: "Високий пріоритет — позиції 4–20, сильний потенціал для росту.",
    medium: "Середній пріоритет — позиції 21–50.",
    low: "Низький пріоритет — далекі позиції або ТОП-3 (утримання).",
};
const DYNAMICS_TOOLTIPS = {
    growth: "Зростання — позиція покращилась порівняно з попереднім періодом.",
    stable: "Стабільно — позиція без значних змін.",
    decline: "Падіння — позиція погіршилась. Потрібна підтримка.",
};

function escapeTitle(s) {
    if (s == null || s === undefined) return "";
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

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
        state.settingsHistory = data.settings_history || [];
        state.selectedUrls = new Set(data.selected_urls || []);
        state.customLinks = data.custom_links || {};

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
            renderStatistics();
        } else if (state.settings) {
            renderSettings();
        }

        loadCollabColumns();
        loadSettingsPresets();
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
let uploadValidationState = { positions: null, ahrefs: null };
let validateUploadTimeout = null;

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
            const statusEl = zone.closest(".upload-card").querySelector(".upload-status");
            statusEl.innerHTML = `<i class="fas fa-check-circle"></i> ${file.name} (${formatSize(file.size)})`;
            statusEl.classList.remove("error");
            uploadValidationState[inputId === "positions-file" ? "positions" : "ahrefs"] = null;
            scheduleValidateUpload();
        } else {
            zone.classList.remove("has-file");
            zone.closest(".upload-card").querySelector(".upload-status").innerHTML = "";
            zone.closest(".upload-card").querySelector(".upload-validation-msg").innerHTML = "";
            zone.closest(".upload-card").querySelector(".upload-validation-msg").className = "upload-validation-msg";
            uploadValidationState[inputId === "positions-file" ? "positions" : "ahrefs"] = null;
            checkCanAnalyze();
        }
    });
});

function scheduleValidateUpload() {
    clearTimeout(validateUploadTimeout);
    validateUploadTimeout = setTimeout(validateUpload, 400);
}

async function validateUpload() {
    const positionsFile = document.getElementById("positions-file").files[0];
    const ahrefsFile = document.getElementById("ahrefs-file").files[0];

    const posStatus = document.getElementById("positions-status");
    const posValidation = document.getElementById("positions-validation");
    const ahrefsStatus = document.getElementById("ahrefs-status");
    const ahrefsValidation = document.getElementById("ahrefs-validation");

    if (positionsFile) {
        posValidation.textContent = "Перевіряємо...";
        posValidation.className = "upload-validation-msg validating";
    }
    if (ahrefsFile) {
        ahrefsValidation.textContent = "Перевіряємо...";
        ahrefsValidation.className = "upload-validation-msg validating";
    }

    const formData = new FormData();
    if (positionsFile) formData.append("positions", positionsFile);
    if (ahrefsFile) formData.append("ahrefs", ahrefsFile);

    if (!positionsFile && !ahrefsFile) {
        checkCanAnalyze();
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/validate-upload`, { method: "POST", body: formData });
        const data = await resp.json();

        if (positionsFile) {
            const r = data.positions || {};
            if (r.ok) {
                posValidation.textContent = `✓ ${r.rows ?? 0} записів знайдено`;
                posValidation.className = "upload-validation-msg success";
                posStatus.classList.remove("error");
                uploadValidationState.positions = true;
            } else {
                posValidation.textContent = r.error || "Помилка валідації";
                posValidation.className = "upload-validation-msg error";
                posStatus.classList.add("error");
                uploadValidationState.positions = false;
            }
        }

        if (ahrefsFile) {
            const r = data.ahrefs || {};
            if (r.ok) {
                ahrefsValidation.textContent = `✓ ${r.rows ?? 0} записів знайдено`;
                ahrefsValidation.className = "upload-validation-msg success";
                ahrefsStatus.classList.remove("error");
                uploadValidationState.ahrefs = true;
            } else {
                ahrefsValidation.textContent = r.error || "Помилка валідації";
                ahrefsValidation.className = "upload-validation-msg error";
                ahrefsStatus.classList.add("error");
                uploadValidationState.ahrefs = false;
            }
        }
    } catch (err) {
        if (positionsFile) {
            posValidation.textContent = "Помилка: " + err.message;
            posValidation.className = "upload-validation-msg error";
            uploadValidationState.positions = false;
        }
        if (ahrefsFile) {
            ahrefsValidation.textContent = "Помилка: " + err.message;
            ahrefsValidation.className = "upload-validation-msg error";
            uploadValidationState.ahrefs = false;
        }
    }

    checkCanAnalyze();
}

const UPLOAD_EXAMPLES = {
    positions: {
        filename: "positions-example.csv",
        content: "URL,Keyword,2024-01-15,2024-02-15\nhttps://example.com/page,ключове слово,12,8\nhttps://example.com/blog,crm система,25,18",
    },
    ahrefs: {
        filename: "ahrefs-example.csv",
        content: "Target URL,Anchor,Referring Page,Type\nhttps://example.com/page,ключове слово,https://site.com/article,dofollow\nhttps://example.com/page,тут,https://other.com/post,nofollow",
    },
};

document.querySelectorAll(".upload-download-example").forEach((btn) => {
    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const ex = UPLOAD_EXAMPLES[btn.dataset.example];
        if (!ex) return;
        const blob = new Blob(["\ufeff" + ex.content], { type: "text/csv;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = ex.filename;
        a.click();
        URL.revokeObjectURL(a.href);
    });
});

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
}

function checkCanAnalyze() {
    const hasPos = document.getElementById("positions-file").files.length > 0;
    const hasAhrefs = document.getElementById("ahrefs-file").files.length > 0;
    const posOk = !hasPos || uploadValidationState.positions === true;
    const ahrefsOk = !hasAhrefs || uploadValidationState.ahrefs === true;
    const validating = (hasPos && uploadValidationState.positions === null) || (hasAhrefs && uploadValidationState.ahrefs === null);
    document.getElementById("analyze-btn").disabled = !(hasPos && hasAhrefs && posOk && ahrefsOk && !validating);
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
        state.customLinks = data.custom_links || {};

        enableNav();
        renderDashboard();
        renderPlan();
        renderSettings();
        renderStatistics();
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

    applyDashboardFiltersAndSort();
    updateSelectionBar();
}

function sortDashboardData(data, column, direction) {
    const asc = direction === "asc";
    const mult = asc ? 1 : -1;

    return [...data].sort((a, b) => {
        let va, vb;
        switch (column) {
            case "url":
                va = (a.url || "").toLowerCase();
                vb = (b.url || "").toLowerCase();
                return mult * (va < vb ? -1 : va > vb ? 1 : 0);
            case "recommendation":
                va = REC_ORDER[a.recommendation] ?? 99;
                vb = REC_ORDER[b.recommendation] ?? 99;
                return mult * (va - vb);
            case "priority":
                va = PRIORITY_ORDER[a.priority] ?? 99;
                vb = PRIORITY_ORDER[b.priority] ?? 99;
                return mult * (va - vb);
            case "best_keyword":
                va = (a.best_keyword?.keyword || "").toLowerCase();
                vb = (b.best_keyword?.keyword || "").toLowerCase();
                return mult * (va < vb ? -1 : va > vb ? 1 : 0);
            case "position":
                va = a.best_keyword?.current_position ?? 999;
                vb = b.best_keyword?.current_position ?? 999;
                return mult * (va - vb);
            case "dynamics":
                va = DYNAMICS_ORDER[a.best_keyword?.dynamics_label] ?? 99;
                vb = DYNAMICS_ORDER[b.best_keyword?.dynamics_label] ?? 99;
                return mult * (va - vb);
            case "total_backlinks":
                va = a.total_backlinks ?? 0;
                vb = b.total_backlinks ?? 0;
                return mult * (va - vb);
            case "dofollow_count":
                va = a.dofollow_count ?? 0;
                vb = b.dofollow_count ?? 0;
                return mult * (va - vb);
            case "recommended_links":
                va = state.customLinks[a.url] ?? a.recommended_links ?? 0;
                vb = state.customLinks[b.url] ?? b.recommended_links ?? 0;
                return mult * (va - vb);
            case "unique_anchors":
                va = a.anchor_profile?.unique_anchors ?? 0;
                vb = b.anchor_profile?.unique_anchors ?? 0;
                return mult * (va - vb);
            case "priority_score":
            default:
                va = a.priority_score ?? 0;
                vb = b.priority_score ?? 0;
                return mult * (vb - va);
        }
    });
}

function applyDashboardFiltersAndSort() {
    const search = document.getElementById("dashboard-search").value.toLowerCase();
    const priority = document.getElementById("priority-filter").value;
    const rec = document.getElementById("recommendation-filter").value;

    let filtered = state.analysis;
    if (search) filtered = filtered.filter((p) =>
        p.url.toLowerCase().includes(search) || (p.keywords || []).some((k) => k.keyword.toLowerCase().includes(search)));
    if (priority) filtered = filtered.filter((p) => p.priority === priority);
    if (rec) filtered = filtered.filter((p) => p.recommendation === rec);

    const sorted = sortDashboardData(filtered, state.dashboardSort.column, state.dashboardSort.direction);
    renderDashboardTable(sorted);
    updateDashboardSortIcons();
}

function updateDashboardSortIcons() {
    document.querySelectorAll("#dashboard-table th[data-sort]").forEach((th) => {
        const col = th.dataset.sort;
        const isActive = col === state.dashboardSort.column;
        const icon = th.querySelector(".sort-icon");
        if (icon) icon.remove();
        const i = document.createElement("span");
        i.className = "sort-icon";
        if (isActive) {
            i.textContent = state.dashboardSort.direction === "asc" ? " ↑" : " ↓";
            i.title = "Клік для зміни напрямку";
        } else {
            i.textContent = " ⇅";
            i.classList.add("sort-inactive");
            i.title = "Клік для сортування";
        }
        th.appendChild(i);
    });
}

function renderDashboardTable(data) {
    const tbody = document.querySelector("#dashboard-table tbody");
    tbody.innerHTML = data.map((page) => {
        const checked = state.selectedUrls.has(page.url) ? "checked" : "";
        const rowCls = checked ? "row-selected" : "";
        const rec = page.recommendation || "not_recommended";
        const linksVal = state.customLinks[page.url] ?? page.recommended_links ?? 3;
        const dyn = page.best_keyword?.dynamics_label || "stable";
        const pos = page.best_keyword?.current_position;
        const kwText = page.best_keyword ? page.best_keyword.keyword : "";
        const posTip = pos != null ? `Позиція по кращому ключу на останню дату` : "Немає даних по позиціях";
        const kwTip = kwText ? `Кращий ключ: ${kwText}${pos != null ? ` (поз. ${pos})` : ""}` : "Немає ключових слів для цього URL";
        const dynTip = DYNAMICS_TOOLTIPS[dyn] || "Динаміка позиції ключа";
        return `
        <tr class="${rowCls}">
            <td title="Включити цей URL в анкор-план"><input type="checkbox" class="url-cb" data-url="${escapeTitle(page.url)}" ${checked}></td>
            <td class="url-cell" title="${escapeTitle(page.url)}"><a href="detail.html?project=${encodeURIComponent(projectId)}&url=${encodeURIComponent(page.url)}" title="${escapeTitle(page.url)} — клік для детальної статистики анкорів">${shortenUrl(page.url)}</a></td>
            <td title="${escapeTitle(REC_TOOLTIPS[rec] || "")}"><span class="badge badge-${rec}">${REC_LABELS[rec] || rec}</span></td>
            <td title="${escapeTitle(PRIORITY_TOOLTIPS[page.priority] || "")}"><span class="badge badge-${page.priority}">${page.priority.toUpperCase()}</span></td>
            <td title="${escapeTitle(kwTip)}">${kwText || "—"}</td>
            <td title="${escapeTitle(posTip)}">${pos ?? "—"}</td>
            <td class="dynamics-${dyn}" title="${escapeTitle(dynTip)}">${getDynamicsIcon(dyn)} ${dyn || "—"}</td>
            <td title="Загальна кількість зворотних посилань на цю сторінку">${page.total_backlinks}</td>
            <td title="Кількість dofollow-посилань серед усіх беклінків">${page.dofollow_count}</td>
            <td title="Рекомендована кількість посилань для закупки. Можна змінити вручну."><input type="number" class="links-input" data-url="${escapeTitle(page.url)}" value="${linksVal}" min="1" max="20" style="width:52px;text-align:center"></td>
            <td title="Кількість унікальних текстів анкорів серед існуючих беклінків">${page.anchor_profile?.unique_anchors ?? 0}</td>
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

    tbody.querySelectorAll(".links-input").forEach((input) => {
        input.addEventListener("change", () => {
            const url = input.dataset.url;
            const val = parseInt(input.value) || 1;
            input.value = Math.max(1, Math.min(20, val));
            state.customLinks[url] = parseInt(input.value);
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
    let totalLinks = 0;
    for (const url of state.selectedUrls) {
        const page = state.analysis.find((p) => p.url === url);
        totalLinks += state.customLinks[url] ?? page?.recommended_links ?? 3;
    }
    document.getElementById("selection-count").textContent =
        `Обрано: ${selected} з ${total} | Лінків: ${totalLinks}`;
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
            body: JSON.stringify({ selected_urls: [...state.selectedUrls], custom_links: state.customLinks }),
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

// Dashboard sort - delegate to thead
document.querySelector("#dashboard-table thead").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort]");
    if (th) setDashboardSort(th.dataset.sort);
});

function filterDashboard() {
    applyDashboardFiltersAndSort();
}

function setDashboardSort(column) {
    if (state.dashboardSort.column === column) {
        state.dashboardSort.direction = state.dashboardSort.direction === "asc" ? "desc" : "asc";
    } else {
        state.dashboardSort.column = column;
        state.dashboardSort.direction = "asc";
        if (["position", "total_backlinks", "dofollow_count", "recommended_links", "unique_anchors", "priority_score"].includes(column)) {
            state.dashboardSort.direction = "desc";
        }
    }
    applyDashboardFiltersAndSort();
}

// --- Plan ---
function renderPlan() { renderPlanTable(state.plan); }

function renderPlanTable(data) {
    const tbody = document.querySelector("#plan-table tbody");
    const realIndexes = data.map((item) => state.plan.indexOf(item));

    tbody.innerHTML = data.map((item, localIdx) => {
        const realIdx = realIndexes[localIdx];
        const order = item.purchase_order || 6;
        const checked = state.selectedPlanRows.has(realIdx) ? "checked" : "";
        const notInPositions = item.anchor_in_positions === false;
        const rowCls = [
            item.is_manual ? "manual-edit" : "",
            checked ? "row-selected" : "",
            notInPositions ? "anchor-not-in-positions" : "",
        ].filter(Boolean).join(" ");
        const manualBadge = item.is_manual ? '<span class="badge-manual">Ручний</span>' : "";
        const rowTitle = notInPositions ? ' title="Позицій не знайдено"' : "";
        return `
        <tr class="${rowCls}"${rowTitle}>
            <td><input type="checkbox" class="plan-cb" data-idx="${realIdx}" ${checked}></td>
            <td><span class="order-badge order-${order}">${order}</span></td>
            <td class="url-cell"><a href="detail.html?project=${encodeURIComponent(projectId)}&url=${encodeURIComponent(item.url)}" title="${item.url}">${shortenUrl(item.url)}</a></td>
            <td class="editable-cell" data-row="${realIdx}">${item.recommended_anchor}${manualBadge}</td>
            <td><span class="badge badge-${item.anchor_type}">${formatAnchorType(item.anchor_type)}</span></td>
            <td>${item.target_keyword || "—"}</td>
            <td>${item.current_position ?? "—"}</td>
            <td class="dynamics-${item.dynamics}">${getDynamicsIcon(item.dynamics)} ${item.dynamics}</td>
            <td class="rationale-text">${item.rationale || item.comment || ""}</td>
            <td><button class="btn-icon edit-row-btn" data-row="${realIdx}" title="Редагувати"><i class="fas fa-pen"></i></button></td>
        </tr>`;
    }).join("");

    tbody.querySelectorAll(".edit-row-btn").forEach((btn) =>
        btn.addEventListener("click", () => openEditModal(parseInt(btn.dataset.row))));
    tbody.querySelectorAll(".editable-cell").forEach((cell) =>
        cell.addEventListener("dblclick", () => openEditModal(parseInt(cell.dataset.row))));

    tbody.querySelectorAll(".plan-cb").forEach((cb) => {
        cb.addEventListener("change", () => {
            const idx = parseInt(cb.dataset.idx);
            if (cb.checked) state.selectedPlanRows.add(idx);
            else state.selectedPlanRows.delete(idx);
            cb.closest("tr").classList.toggle("row-selected", cb.checked);
            updatePlanSelectionBar();
        });
    });

    updatePlanSelectionBar();
}

function updatePlanSelectionBar() {
    const bar = document.getElementById("plan-selection-bar");
    const count = state.selectedPlanRows.size;
    document.getElementById("plan-selection-count").textContent = `Обрано: ${count}`;
    bar.style.display = count > 0 ? "flex" : "none";
}

// Plan upload modal
let pendingUploadFile = null;

document.getElementById("btn-upload-plan").addEventListener("click", () => {
    pendingUploadFile = null;
    const nameEl = document.getElementById("upload-plan-file-name");
    nameEl.textContent = "Файл не обрано";
    nameEl.classList.remove("has-file");
    document.getElementById("upload-plan-confirm").disabled = true;
    document.getElementById("anchor-plan-file").value = "";
    document.getElementById("upload-plan-modal").style.display = "flex";
});

document.getElementById("anchor-plan-file").addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    pendingUploadFile = file || null;
    const nameEl = document.getElementById("upload-plan-file-name");
    nameEl.textContent = file ? file.name : "Файл не обрано";
    nameEl.classList.toggle("has-file", !!file);
    document.getElementById("upload-plan-confirm").disabled = !file;
});

function closeUploadPlanModal() {
    document.getElementById("upload-plan-modal").style.display = "none";
    pendingUploadFile = null;
}

document.getElementById("upload-plan-modal-close").addEventListener("click", closeUploadPlanModal);
document.getElementById("upload-plan-cancel").addEventListener("click", closeUploadPlanModal);
document.getElementById("upload-plan-modal").addEventListener("click", (e) => {
    if (e.target.id === "upload-plan-modal") closeUploadPlanModal();
});

document.getElementById("upload-plan-confirm").addEventListener("click", async () => {
    if (!pendingUploadFile) return;

    const mode = document.querySelector('input[name="plan-upload-mode"]:checked')?.value || "replace";
    const formData = new FormData();
    formData.append("anchor_plan", pendingUploadFile);
    formData.append("mode", mode);

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/plan/upload`, {
            method: "POST",
            body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) {
            alert(data.error || "Помилка завантаження");
            return;
        }
        state.plan = data.plan;
        renderPlan();
        switchSection("plan");
        closeUploadPlanModal();
    } catch (err) {
        alert("Помилка: " + err.message);
    }
});

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
let editAnchorOptions = [];

async function openEditModal(rowIndex) {
    state.editingRowIndex = rowIndex;
    const item = state.plan[rowIndex];
    const input = document.getElementById("edit-anchor-text");
    input.value = item.recommended_anchor;
    document.getElementById("edit-anchor-type").value = item.anchor_type;
    document.getElementById("edit-anchor-dropdown").classList.remove("open");
    document.getElementById("edit-modal").style.display = "flex";

    editAnchorOptions = [];
    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/plan/available-anchors?url=${encodeURIComponent(item.url || "")}`);
        const data = await resp.json();
        if (resp.ok && data.anchors && data.anchors.length > 0) {
            editAnchorOptions = data.anchors;
        }
    } catch (e) { /* ignore */ }
    renderEditAnchorOptions();
}

function renderEditAnchorOptions(filter = "") {
    const container = document.getElementById("edit-anchor-options");
    const emptyEl = document.getElementById("edit-anchor-empty");
    container.innerHTML = "";
    const q = filter.trim().toLowerCase();
    const filtered = q ? editAnchorOptions.filter((a) => a.toLowerCase().includes(q)) : editAnchorOptions;
    filtered.forEach((a) => {
        const opt = document.createElement("div");
        opt.className = "edit-anchor-option";
        opt.textContent = a;
        opt.addEventListener("click", () => {
            document.getElementById("edit-anchor-text").value = a;
            document.getElementById("edit-anchor-dropdown").classList.remove("open");
        });
        container.appendChild(opt);
    });
    emptyEl.style.display = filtered.length === 0 ? "block" : "none";
}

function setupEditAnchorCombobox() {
    const input = document.getElementById("edit-anchor-text");
    const dropdown = document.getElementById("edit-anchor-dropdown");
    const arrow = document.querySelector(".edit-anchor-arrow");

    function toggleDropdown() {
        dropdown.classList.toggle("open");
        if (dropdown.classList.contains("open")) renderEditAnchorOptions(input.value);
    }

    input.addEventListener("focus", () => dropdown.classList.add("open"));
    input.addEventListener("input", () => {
        if (dropdown.classList.contains("open")) renderEditAnchorOptions(input.value);
    });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Escape") dropdown.classList.remove("open");
    });
    if (arrow) arrow.addEventListener("click", (e) => { e.preventDefault(); toggleDropdown(); });

    document.addEventListener("click", (e) => {
        if (!e.target.closest(".edit-anchor-combobox")) dropdown.classList.remove("open");
    });
}

document.getElementById("modal-close").addEventListener("click", closeModal);
document.getElementById("modal-cancel").addEventListener("click", closeModal);
document.getElementById("edit-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("edit-modal")) closeModal();
});
setupEditAnchorCombobox();

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

const DIST_TOOLTIPS = {
    exact_match: "Точне збігання з ключовим словом",
    partial_match: "Часткове збігання (містить ключове слово)",
    branded: "Брендовані (назва бренду)",
    generic: "Загальні (інші слова)",
    url: "URL / голий посилання",
};

// --- Settings ---
function renderSettings() {
    if (!state.settings) return;
    const dist = state.settings.anchor_distribution || {};
    const distContainer = document.getElementById("distribution-settings");
    const typeLabels = { exact_match: "Exact Match", partial_match: "Partial Match", branded: "Branded", generic: "Generic", url: "URL / Naked Link" };

    distContainer.innerHTML = Object.entries(dist).map(([key, val]) => {
        const t = val || {};
        const tip = DIST_TOOLTIPS[key] || "";
        return `<div class="field-row">
            <label class="with-tooltip">${typeLabels[key] || key} ${tip ? `<i class="fas fa-info-circle" data-tooltip="${tip}"></i>` : ""}</label>
            <input type="number" data-dist="${key}" data-bound="min" value="${t.min ?? 0}" min="0" max="100" style="width:60px">
            <span class="range-sep">—</span>
            <input type="number" data-dist="${key}" data-bound="max" value="${t.max ?? 0}" min="0" max="100" style="width:60px">
            <span class="range-sep">%</span>
        </div>`;
    }).join("");

    const prioRanges = state.settings.priority_ranges || {};
    const prioContainer = document.getElementById("priority-settings");
    const prioLabels = { high: "Високий", medium: "Середній", low_top: "Низький (ТОП)", low_bottom: "Низький (дно)" };
    const prioTooltips = {
        high: "Основні кандидати для закупок. Найбільший потенціал росту.",
        medium: "Другорядний пріоритет. Потребують підтримки для виходу в ТОП.",
        low_top: "Утримання. Вже в ТОП-3, менше потребують посилань.",
        low_bottom: "Далекі позиції. Низький пріоритет або спостереження.",
    };

    prioContainer.innerHTML = Object.entries(prioRanges).map(([key, val]) => {
        const v = val || {};
        const tip = prioTooltips[key] || "";
        return `<div class="field-row priority-range-row">
            <label class="with-tooltip">${prioLabels[key] || key} ${tip ? `<i class="fas fa-info-circle" data-tooltip="${tip}"></i>` : ""}</label>
            <input type="number" data-prio="${key}" data-bound="from" value="${v.from ?? 1}" min="1" max="1000" style="width:60px">
            <span class="range-sep">—</span>
            <input type="number" data-prio="${key}" data-bound="to" value="${v.to ?? 1}" min="1" max="1000" style="width:60px">
            <span class="range-sep">поз.</span>
            <span class="range-sep" style="margin-left:8px">бал:</span>
            <span class="priority-score-cell">
                <input type="number" data-prio="${key}" data-bound="base_score" value="${v.base_score ?? 40}" min="0" max="100" class="priority-base-score-input">
                <i class="fas fa-info-circle" data-tooltip="Базовий бал для цього діапазону. Впливає на priority_score і сортування сторінок. Чим вищий бал — тим вищий пріоритет сторінок у цьому діапазоні."></i>
            </span>
        </div>`;
    }).join("");

    renderPriorityVisualBar();
    updatePriorityPreview();
    updatePriorityCoverage();
    bindPriorityTemplateButtons();
    document.querySelectorAll("#priority-settings input").forEach((inp) => {
        inp.addEventListener("input", () => { renderPriorityVisualBar(); updatePriorityPreview(); updatePriorityCoverage(); });
        inp.addEventListener("change", () => { renderPriorityVisualBar(); updatePriorityPreview(); updatePriorityCoverage(); });
    });

    const brandVal = state.settings.brand_name;
    document.getElementById("settings-brand").value = Array.isArray(brandVal) ? brandVal.join(", ") : (brandVal || "");
    document.getElementById("settings-links-per-page").value = state.settings.links_per_page || 3;
    document.getElementById("settings-budget").value = state.settings.monthly_budget || 0;
    document.getElementById("settings-planned-links").value = state.settings.planned_links_count || 0;
    const currencyEl = document.getElementById("settings-currency");
    if (currencyEl) currencyEl.value = state.settings.currency || "UAH";

    renderSettingsHistorySelect();
    updateBudgetForecast();
    renderPresetSelect();
}

function renderSettingsHistorySelect() {
    const sel = document.getElementById("settings-history-select");
    if (!sel) return;
    sel.innerHTML = '<option value="">— Немає історії —</option>';
    (state.settingsHistory || []).forEach((h, i) => {
        const d = h.created_at ? new Date(h.created_at).toLocaleString("uk-UA") : `Версія ${i + 1}`;
        sel.appendChild(new Option(d, String(i)));
    });
}

function renderPresetSelect() {
    const sel = document.getElementById("settings-preset-select");
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="">— Оберіть шаблон —</option>';
    (state.settingsPresets || []).forEach((p) => {
        sel.appendChild(new Option(p.name, p.id));
    });
    sel.value = cur || "";
}

async function loadSettingsPresets() {
    try {
        const resp = await fetch(`${API_BASE}/settings-presets`);
        if (!resp.ok) return;
        const data = await resp.json();
        state.settingsPresets = data.presets || [];
        if (document.getElementById("settings-preset-select")) renderPresetSelect();
    } catch (e) {}
}

function updateBudgetForecast() {
    const el = document.getElementById("settings-budget-forecast");
    if (!el) return;
    const budget = parseFloat(document.getElementById("settings-budget")?.value || 0);
    const currency = document.getElementById("settings-currency")?.value || "UAH";
    const total = state.purchaseStats?.total_cost ?? 0;
    if (budget <= 0 || total <= 0) {
        el.style.display = "none";
        return;
    }
    el.style.display = "block";
    el.className = "settings-budget-forecast" + (total > budget ? " over-budget" : "");
    el.textContent = `Прогноз витрат: ${total.toLocaleString("uk-UA")} ${currency}${total > budget ? " (перевищення бюджету)" : ""}`;
}

function showSettingsValidation(msg, isError = true) {
    const el = document.getElementById("settings-validation-msg");
    if (!el) return;
    el.textContent = msg;
    el.className = "settings-validation-msg " + (isError ? "error" : "success");
    el.style.display = msg ? "block" : "none";
}

const PRIORITY_PRESETS = {
    standard: { high: { from: 4, to: 20, base_score: 80 }, medium: { from: 21, to: 50, base_score: 40 }, low_top: { from: 1, to: 3, base_score: 20 }, low_bottom: { from: 51, to: 1000, base_score: 5 } },
    conservative: { high: { from: 4, to: 15, base_score: 80 }, medium: { from: 16, to: 40, base_score: 40 }, low_top: { from: 1, to: 3, base_score: 20 }, low_bottom: { from: 41, to: 1000, base_score: 5 } },
    aggressive: { high: { from: 4, to: 30, base_score: 80 }, medium: { from: 31, to: 80, base_score: 40 }, low_top: { from: 1, to: 3, base_score: 20 }, low_bottom: { from: 81, to: 1000, base_score: 5 } },
};

function getCurrentPriorityRanges() {
    const ranges = {};
    document.querySelectorAll("[data-prio]").forEach((input) => {
        const key = input.dataset.prio, bound = input.dataset.bound;
        if (!ranges[key]) ranges[key] = {};
        ranges[key][bound] = parseInt(input.value) || (bound === "base_score" ? 40 : 1);
    });
    return ranges;
}

function renderPriorityVisualBar() {
    const el = document.getElementById("priority-visual-bar");
    if (!el) return;
    const ranges = getCurrentPriorityRanges();
    const order = ["low_top", "high", "medium", "low_bottom"];
    const colors = { low_top: "#6b7280", high: "#22c55e", medium: "#eab308", low_bottom: "#ef4444" };
    const labels = { low_top: "ТОП", high: "Вис.", medium: "Сер.", low_bottom: "Низ." };
    const maxPos = 100;
    const segments = [];
    for (let pos = 1; pos <= maxPos; pos++) {
        let found = false;
        for (const key of order) {
            const r = ranges[key];
            if (!r) continue;
            const f = r.from ?? 1, t = r.to ?? 1000;
            if (f <= pos && pos <= t) {
                segments.push({ pos, key, color: colors[key] || "#999", label: labels[key] });
                found = true;
                break;
            }
        }
        if (!found) segments.push({ pos, key: "gap", color: "#333", label: "" });
    }
    el.innerHTML = segments.map((s) =>
        `<span class="priority-bar-seg" style="width:1%;background:${s.color}" title="Поз. ${s.pos}: ${s.label || 'дірка'}"></span>`
    ).join("");
}

function updatePriorityPreview() {
    const el = document.getElementById("priority-preview");
    if (!el || !state.analysis?.length) { if (el) el.style.display = "none"; return; }
    const ranges = getCurrentPriorityRanges();
    const counts = { high: 0, medium: 0, low: 0 };
    for (const page of state.analysis) {
        const kw = page.keywords || [];
        let bestPos = null;
        for (const k of kw) {
            const p = k.current_position;
            if (p != null && (bestPos == null || p < bestPos)) bestPos = p;
        }
        if (bestPos == null) { counts.low++; continue; }
        if (ranges.low_top && bestPos >= ranges.low_top.from && bestPos <= ranges.low_top.to) { counts.low++; continue; }
        if (ranges.high && bestPos >= ranges.high.from && bestPos <= ranges.high.to) { counts.high++; continue; }
        if (ranges.medium && bestPos >= ranges.medium.from && bestPos <= ranges.medium.to) { counts.medium++; continue; }
        if (ranges.low_bottom && bestPos >= ranges.low_bottom.from && bestPos <= ranges.low_bottom.to) { counts.low++; continue; }
        counts.low++;
    }
    el.style.display = "block";
    el.innerHTML = `<div class="priority-preview-label">Розподіл сторінок:</div>
        <span class="priority-preview-high">Високий: ${counts.high}</span>
        <span class="priority-preview-medium">Середній: ${counts.medium}</span>
        <span class="priority-preview-low">Низький: ${counts.low}</span>`;
}

function updatePriorityCoverage() {
    const el = document.getElementById("priority-coverage-msg");
    if (!el) return;
    const ranges = getCurrentPriorityRanges();
    const order = ["low_top", "high", "medium", "low_bottom"];
    const sorted = order.map((k) => ({ key: k, from: ranges[k]?.from ?? 1, to: ranges[k]?.to ?? 1000 })).sort((a, b) => a.from - b.from);
    const gaps = [];
    for (let i = 0; i < sorted.length - 1; i++) {
        const end = sorted[i].to, nextStart = sorted[i + 1].from;
        if (nextStart > end + 1) gaps.push({ from: end + 1, to: nextStart - 1 });
    }
    if (gaps.length > 0) {
        el.style.display = "block";
        el.className = "priority-coverage-msg warning";
        el.textContent = "Обережно: є дірки в діапазонах (позиції " + gaps.map((g) => `${g.from}–${g.to}`).join(", ") + " не покриті).";
    } else {
        el.style.display = "none";
    }
}

function bindPriorityTemplateButtons() {
    document.querySelectorAll(".priority-template-btn").forEach((btn) => {
        btn.onclick = () => {
            const preset = PRIORITY_PRESETS[btn.dataset.preset];
            if (!preset) return;
            const prioContainer = document.getElementById("priority-settings");
            prioContainer.querySelectorAll("[data-prio]").forEach((input) => {
                const key = input.dataset.prio, bound = input.dataset.bound;
                const val = preset[key]?.[bound];
                if (val != null) input.value = val;
            });
            state.settings = state.settings || {};
            state.settings.priority_ranges = JSON.parse(JSON.stringify(preset));
            renderPriorityVisualBar();
            updatePriorityPreview();
            updatePriorityCoverage();
        };
    });
}

// --- Save Settings (without recalc) ---
document.getElementById("save-settings-btn").addEventListener("click", async () => {
    const newSettings = collectSettings();
    const btn = document.getElementById("save-settings-btn");
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Зберігаємо...';

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/settings`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ settings: newSettings }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.settings = data.settings;
            state.settingsHistory = data.settings_history || [];
            renderSettings();
            renderSettingsHistorySelect();
            showSettingsValidation("Налаштування збережено", false);
            setTimeout(() => showSettingsValidation(""), 2000);
        } else {
            showSettingsValidation(data.error || "Помилка збереження");
        }
    } catch (err) {
        showSettingsValidation("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-save"></i> Зберегти налаштування';
    }
});

// --- Recalculate ---
document.getElementById("recalculate-btn").addEventListener("click", async () => {
    const newSettings = collectSettings();
    const btn = document.getElementById("recalculate-btn");
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Перераховуємо...';
    showSettingsValidation("");

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/recalculate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ settings: newSettings, selected_urls: [...state.selectedUrls], custom_links: state.customLinks }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.plan = data.plan;
            state.analysis = data.analysis || state.analysis;
            state.settings = data.settings;
            state.settingsHistory = data.settings_history || [];
            renderPlan();
            renderSettings();
            renderDashboard();
            renderStatistics();
            switchSection("plan");
        } else {
            showSettingsValidation(data.error || "Помилка");
        }
    } catch (err) {
        showSettingsValidation("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync-alt"></i> Перерахувати план';
    }
});

// --- Presets ---
document.getElementById("settings-preset-select").addEventListener("change", (e) => {
    const id = e.target.value;
    if (!id) return;
    const preset = state.settingsPresets.find((p) => p.id === id);
    if (!preset || !preset.settings) return;
    applyPresetToForm(preset.settings);
    e.target.value = "";
});

function applyPresetToForm(settings) {
    if (!settings || !state.settings) return;
    state.settings = { ...state.settings, ...settings };
    if (settings.anchor_distribution) state.settings.anchor_distribution = settings.anchor_distribution;
    if (settings.priority_ranges) state.settings.priority_ranges = settings.priority_ranges;
    renderSettings();
}

document.getElementById("btn-save-as-preset").addEventListener("click", async () => {
    const name = prompt("Назва шаблону:", "");
    if (!name?.trim()) return;
    const settings = collectSettings();
    try {
        const resp = await fetch(`${API_BASE}/settings-presets`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name.trim(), settings }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.settingsPresets.push({ id: data.id, name: data.name, settings: data.settings });
            renderPresetSelect();
            showSettingsValidation("Шаблон збережено", false);
            setTimeout(() => showSettingsValidation(""), 2000);
        } else alert(data.error || "Помилка");
    } catch (err) { alert("Помилка: " + err.message); }
});

// --- Reset ---
document.getElementById("btn-reset-settings").addEventListener("click", async () => {
    if (!confirm("Скинути налаштування до стандартних?")) return;
    const defaults = {
        brand_name: "", monthly_budget: 0, planned_links_count: 0, currency: "UAH",
        anchor_distribution: { exact_match: { min: 10, max: 15 }, partial_match: { min: 20, max: 25 }, branded: { min: 20, max: 30 }, generic: { min: 15, max: 20 }, url: { min: 10, max: 15 } },
        priority_ranges: { high: { from: 4, to: 20, base_score: 80 }, medium: { from: 21, to: 50, base_score: 40 }, low_top: { from: 1, to: 3, base_score: 20 }, low_bottom: { from: 51, to: 1000, base_score: 5 } },
        links_per_page: 3, site_filters: state.settings?.site_filters || [],
    };
    state.settings = { ...state.settings, ...defaults };
    renderSettings();
});

// --- Export / Import ---
document.getElementById("btn-export-settings").addEventListener("click", () => {
    const settings = collectSettings();
    const blob = new Blob([JSON.stringify(settings, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `anchor-plan-settings-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
});

document.getElementById("settings-import-file").addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => {
        try {
            const settings = JSON.parse(r.result);
            if (settings && (settings.anchor_distribution || settings.priority_ranges || settings.brand_name !== undefined)) {
                applyPresetToForm(settings);
                showSettingsValidation("Налаштування імпортовано", false);
                setTimeout(() => showSettingsValidation(""), 2000);
            } else alert("Невірний формат файлу");
        } catch (err) { alert("Помилка читання JSON"); }
    };
    r.readAsText(f);
    e.target.value = "";
});

// --- History ---
document.getElementById("settings-history-select").addEventListener("change", async (e) => {
    const idx = e.target.value;
    if (idx === "" || idx === null) return;
    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/restore-settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index: parseInt(idx, 10) }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.settings = data.settings;
            state.settingsHistory = data.settings_history || [];
            renderSettings();
            renderSettingsHistorySelect();
            showSettingsValidation("Налаштування відновлено", false);
            setTimeout(() => showSettingsValidation(""), 2000);
        } else alert(data.error || "Помилка");
    } catch (err) { alert("Помилка: " + err.message); }
    e.target.value = "";
});

// --- Advanced toggles ---
document.getElementById("toggle-distribution").addEventListener("click", () => {
    document.getElementById("toggle-distribution").closest(".settings-card")?.classList.toggle("collapsed");
});
document.getElementById("toggle-priority").addEventListener("click", () => {
    document.getElementById("toggle-priority").closest(".settings-card")?.classList.toggle("collapsed");
});

// --- Budget forecast update ---
document.getElementById("settings-budget").addEventListener("input", updateBudgetForecast);
document.getElementById("settings-currency").addEventListener("change", updateBudgetForecast);

function collectSettings() {
    const settings = {
        anchor_distribution: {}, priority_ranges: {},
        brand_name: document.getElementById("settings-brand")?.value?.trim() || "",
        links_per_page: parseInt(document.getElementById("settings-links-per-page")?.value) || 3,
        monthly_budget: parseFloat(document.getElementById("settings-budget")?.value) || 0,
        planned_links_count: parseInt(document.getElementById("settings-planned-links")?.value) || 0,
        currency: document.getElementById("settings-currency")?.value || "UAH",
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
        const def = bound === "base_score" ? 40 : 1;
        settings.priority_ranges[key][bound] = parseInt(input.value) || def;
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

// --- Plan Select All ---
document.getElementById("plan-select-all-cb").addEventListener("change", (e) => {
    const checked = e.target.checked;
    document.querySelectorAll(".plan-cb").forEach((cb) => {
        const idx = parseInt(cb.dataset.idx);
        cb.checked = checked;
        if (checked) state.selectedPlanRows.add(idx);
        else state.selectedPlanRows.delete(idx);
        cb.closest("tr").classList.toggle("row-selected", checked);
    });
    updatePlanSelectionBar();
});

// --- Delete Selected ---
document.getElementById("btn-delete-selected").addEventListener("click", () => {
    if (state.selectedPlanRows.size === 0) return;
    document.getElementById("confirm-delete-text").textContent =
        `Видалити ${state.selectedPlanRows.size} анкор(ів) з плану?`;
    document.getElementById("confirm-delete-modal").style.display = "flex";
});

document.getElementById("confirm-delete-close").addEventListener("click", () => {
    document.getElementById("confirm-delete-modal").style.display = "none";
});
document.getElementById("confirm-delete-cancel").addEventListener("click", () => {
    document.getElementById("confirm-delete-modal").style.display = "none";
});
document.getElementById("confirm-delete-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("confirm-delete-modal"))
        document.getElementById("confirm-delete-modal").style.display = "none";
});

document.getElementById("confirm-delete-ok").addEventListener("click", async () => {
    document.getElementById("confirm-delete-modal").style.display = "none";
    const indexes = [...state.selectedPlanRows];
    const btn = document.getElementById("btn-delete-selected");
    btn.disabled = true;

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/plan/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ indexes }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.plan = data.plan;
            state.selectedPlanRows.clear();
            document.getElementById("plan-select-all-cb").checked = false;
            renderPlan();
        } else {
            alert(data.error || "Помилка");
        }
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
    }
});

// --- Add Anchor Modal ---
document.getElementById("btn-add-anchor").addEventListener("click", () => {
    const urlSelect = document.getElementById("add-anchor-url");
    const urls = state.selectedUrls.size > 0
        ? [...state.selectedUrls]
        : state.analysis.map((p) => p.url);

    urlSelect.innerHTML = urls.map((u) =>
        `<option value="${u}">${shortenUrl(u)}</option>`
    ).join("");

    document.getElementById("add-anchor-text").value = "";
    document.getElementById("add-anchor-type").value = "partial_match";
    document.getElementById("add-anchor-keyword").value = "";
    document.getElementById("add-anchor-rationale").value = "";
    document.getElementById("add-modal").style.display = "flex";
});

document.getElementById("add-modal-close").addEventListener("click", () => {
    document.getElementById("add-modal").style.display = "none";
});
document.getElementById("add-modal-cancel").addEventListener("click", () => {
    document.getElementById("add-modal").style.display = "none";
});
document.getElementById("add-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("add-modal"))
        document.getElementById("add-modal").style.display = "none";
});

document.getElementById("add-modal-save").addEventListener("click", async () => {
    const url = document.getElementById("add-anchor-url").value;
    const anchor = document.getElementById("add-anchor-text").value.trim();
    const anchorType = document.getElementById("add-anchor-type").value;
    const targetKeyword = document.getElementById("add-anchor-keyword").value.trim();
    const rationale = document.getElementById("add-anchor-rationale").value.trim();

    if (!anchor) { alert("Введіть текст анкору"); return; }

    const btn = document.getElementById("add-modal-save");
    btn.disabled = true;

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/plan/add`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, anchor, anchor_type: anchorType, target_keyword: targetKeyword, rationale }),
        });
        const data = await resp.json();
        if (resp.ok) {
            state.plan = data.plan;
            renderPlan();
            document.getElementById("add-modal").style.display = "none";
        } else {
            alert(data.error || "Помилка");
        }
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
    }
});

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

let filterRowIdCounter = 0;

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

    const initialValues = Array.isArray(valueVal) ? valueVal : (typeof valueVal === "string" && valueVal ? valueVal.split(",").map((s) => s.trim()).filter(Boolean) : []);

    const valueWrapper = document.createElement("div");
    valueWrapper.className = "filter-value-multiselect";

    const valueTrigger = document.createElement("button");
    valueTrigger.type = "button";
    valueTrigger.className = "filter-value-trigger";
    valueTrigger.textContent = initialValues.length ? initialValues.join(", ") : "Оберіть значення";

    const valueDropdown = document.createElement("div");
    valueDropdown.className = "filter-value-dropdown";

    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.className = "filter-value-search";
    searchInput.placeholder = "Пошук...";

    const optionsContainer = document.createElement("div");
    optionsContainer.className = "filter-value-options";

    const emptyState = document.createElement("div");
    emptyState.className = "filter-value-empty";
    emptyState.textContent = "Нічого не знайдено";
    emptyState.style.display = "none";

    const removeBtn = document.createElement("button");
    removeBtn.className = "btn-remove-filter";
    removeBtn.innerHTML = "×";
    removeBtn.addEventListener("click", () => row.remove());

    function updateTriggerLabel() {
        const checked = valueDropdown.querySelectorAll("input:checked");
        const vals = Array.from(checked).map((cb) => cb.value);
        valueTrigger.textContent = vals.length ? vals.join(", ") : "Оберіть значення";
    }

    function updateOps() {
        const opt = fieldSelect.selectedOptions[0];
        const type = opt?.dataset?.type || "text";
        const ops = type === "number" ? NUM_OPS : TEXT_OPS;
        opSelect.innerHTML = ops.map((o) =>
            `<option value="${o.value}" ${o.value === opVal ? "selected" : ""}>${o.label}</option>`
        ).join("");
    }

    function filterOptionsBySearch() {
        const q = searchInput.value.trim().toLowerCase();
        const options = optionsContainer.querySelectorAll(".filter-value-option");
        let visibleCount = 0;
        options.forEach((label) => {
            const text = (label.textContent || "").toLowerCase();
            const match = !q || text.includes(q);
            label.style.display = match ? "" : "none";
            if (match) visibleCount++;
        });
        emptyState.style.display = visibleCount === 0 && options.length > 0 ? "block" : "none";
    }

    async function updateValueDropdown() {
        const field = fieldSelect.value;
        optionsContainer.innerHTML = "";
        searchInput.value = "";
        valueTrigger.textContent = "Оберіть значення";
        if (!field) return;

        const opt = fieldSelect.selectedOptions[0];
        const type = opt?.dataset?.type || "text";
        try {
            const resp = await fetch(`${API_BASE}/projects/${projectId}/collaborator-unique-values?column=${encodeURIComponent(field)}`);
            if (!resp.ok) return;
            const data = await resp.json();
            const values = data.values || [];
            values.forEach((v) => {
                const s = String(v);
                const label = document.createElement("label");
                label.className = "filter-value-option";
                const cb = document.createElement("input");
                cb.type = "checkbox";
                cb.value = s;
                cb.checked = initialValues.some((iv) => String(iv) === s);
                cb.addEventListener("change", updateTriggerLabel);
                label.appendChild(cb);
                label.appendChild(document.createTextNode(s));
                optionsContainer.appendChild(label);
            });
            searchInput.value = "";
            filterOptionsBySearch();
            updateTriggerLabel();
            if (type === "number" && data.min != null && data.max != null) {
                valueTrigger.title = `Мін: ${data.min} — макс: ${data.max}`;
            }
        } catch (e) {}
    }

    valueTrigger.addEventListener("click", (e) => {
        e.stopPropagation();
        const willOpen = !valueDropdown.classList.contains("open");
        valueDropdown.classList.toggle("open");
        if (willOpen) {
            searchInput.value = "";
            filterOptionsBySearch();
            setTimeout(() => searchInput.focus(), 50);
        }
    });

    searchInput.addEventListener("input", filterOptionsBySearch);
    searchInput.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Escape") {
            valueDropdown.classList.remove("open");
            searchInput.blur();
        }
    });

    valueDropdown.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            valueDropdown.classList.remove("open");
            searchInput.blur();
        }
    });

    valueDropdown.addEventListener("click", (e) => e.stopPropagation());

    document.addEventListener("click", (e) => {
        if (!valueWrapper.contains(e.target)) valueDropdown.classList.remove("open");
    });

    fieldSelect.addEventListener("change", () => {
        opVal = "";
        initialValues.length = 0;
        updateOps();
        updateValueDropdown();
    });

    updateOps();
    valueDropdown.appendChild(searchInput);
    valueDropdown.appendChild(optionsContainer);
    valueDropdown.appendChild(emptyState);
    valueWrapper.appendChild(valueTrigger);
    valueWrapper.appendChild(valueDropdown);
    if (fieldVal) updateValueDropdown();

    row.append(fieldSelect, opSelect, valueWrapper, removeBtn);
    container.appendChild(row);
}

function collectFilters() {
    const rows = document.querySelectorAll("#filters-list .filter-row");
    const filters = [];
    rows.forEach((row) => {
        const field = row.querySelector(".field-select")?.value;
        const op = row.querySelector(".op-select")?.value;
        const checked = row.querySelectorAll(".filter-value-dropdown input:checked");
        const values = Array.from(checked).map((cb) => cb.value?.trim()).filter(Boolean);
        const col = state.collabColumns.find((c) => c.name === field);
        const isNum = col?.type === "number";
        let value;
        if (values.length === 0) return;
        if (values.length === 1) {
            value = isNum ? parseFloat(values[0]) || values[0] : values[0];
        } else {
            value = values.map((v) => (isNum ? (parseFloat(v) || v) : v));
        }
        if (field && op) {
            filters.push({ field, op, value });
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

// ==================== Purchases ====================

document.getElementById("btn-match-sites").addEventListener("click", matchSites);
document.getElementById("btn-rematch-sites").addEventListener("click", matchSites);

async function matchSites() {
    const btn = document.getElementById("btn-match-sites");
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Підбираємо...';

    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/match-sites`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });
        const data = await resp.json();
        if (!resp.ok) { alert(data.error || "Помилка"); return; }

        state.purchaseAssignments = data.assignments;
        state.purchaseStats = {
            total_plan: data.total_plan,
            matched: data.matched,
            not_matched: data.not_matched,
            total_cost: data.total_cost,
            remaining_budget: data.remaining_budget,
            filtered_sites_count: data.filtered_sites_count,
        };

        renderPurchases();
        updateBudgetForecast();
        document.getElementById("btn-rematch-sites").style.display = "inline-flex";
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic"></i> Підібрати площадки';
    }
}

function renderPurchases() {
    renderPurchasesStats();
    renderPurchasesTable(state.purchaseAssignments);
}

function renderPurchasesStats() {
    const stats = state.purchaseStats;
    if (!stats) return;

    const budget = state.settings?.monthly_budget || 0;
    document.getElementById("purchases-stats-row").innerHTML = `
        <div class="stat-card total"><div class="stat-value">${stats.total_plan}</div><div class="stat-label">Всього в плані</div></div>
        <div class="stat-card high"><div class="stat-value">${stats.matched}</div><div class="stat-label">Підібрано</div></div>
        <div class="stat-card low"><div class="stat-value">${stats.not_matched}</div><div class="stat-label">Не підібрано</div></div>
        <div class="stat-card medium"><div class="stat-value">${stats.total_cost.toLocaleString()} ₴</div><div class="stat-label">Загальна вартість</div></div>
        ${budget > 0 ? `<div class="stat-card"><div class="stat-value">${stats.remaining_budget.toLocaleString()} ₴</div><div class="stat-label">Залишок бюджету</div></div>` : ""}
        <div class="stat-card"><div class="stat-value">${stats.filtered_sites_count}</div><div class="stat-label">Доступних площадок</div></div>
    `;
}

function renderPurchasesTable(assignments) {
    const tbody = document.querySelector("#purchases-table tbody");
    if (!assignments || !assignments.length) {
        tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:40px;color:var(--text-muted)">Натисніть "Підібрати площадки" для підбору</td></tr>';
        return;
    }

    tbody.innerHTML = assignments.map((a, idx) => {
        const planItem = state.plan[a.plan_index] || {};
        const order = planItem.purchase_order || 6;
        const isMatched = !!a.assigned_site;
        const statusClass = isMatched ? "purchase-status-matched" : "purchase-status-not-matched";
        const statusText = isMatched ? "Підібрано" : "Не підібрано";

        let qualityHtml = "—";
        if (isMatched && a.site_quality) {
            const q = a.site_quality;
            const cls = q >= 70 ? "quality-high" : (q >= 40 ? "quality-mid" : "quality-low");
            qualityHtml = `<div class="quality-bar"><div class="quality-bar-fill"><span class="${cls}" style="width:${q}%"></span></div><span>${q}</span></div>`;
        }

        let domainHtml = "—";
        if (isMatched && a.assigned_site) {
            const short = a.assigned_site.replace(/^https?:\/\//, "").replace(/\/$/, "");
            domainHtml = a.site_url
                ? `<a href="${a.site_url}" target="_blank" class="site-domain-link">${short}</a>`
                : short;
        }

        return `
        <tr>
            <td><span class="order-badge order-${order}">${order}</span></td>
            <td class="url-cell"><a href="detail.html?project=${encodeURIComponent(projectId)}&url=${encodeURIComponent(planItem.url || "")}" title="${planItem.url || ""}">${shortenUrl(planItem.url || "")}</a></td>
            <td>${planItem.recommended_anchor || "—"}</td>
            <td><span class="badge badge-${planItem.anchor_type || ""}">${formatAnchorType(planItem.anchor_type || "")}</span></td>
            <td>${domainHtml}</td>
            <td>${isMatched ? (a.site_dr ?? "—") : "—"}</td>
            <td>${isMatched && a.site_organic != null ? Number(a.site_organic).toLocaleString() : "—"}</td>
            <td>${isMatched ? (a.site_theme || "—") : "—"}</td>
            <td>${isMatched ? Number(a.site_price).toLocaleString() + " ₴" : "—"}</td>
            <td>${qualityHtml}</td>
            <td><span class="${statusClass}">${statusText}</span></td>
            <td><button class="btn-replace" data-plan-index="${a.plan_index}" title="Замінити площадку"><i class="fas fa-exchange-alt"></i></button></td>
        </tr>`;
    }).join("");

    tbody.querySelectorAll(".btn-replace").forEach((btn) => {
        btn.addEventListener("click", () => openReplaceSiteModal(parseInt(btn.dataset.planIndex)));
    });
}

// Purchases filter
document.getElementById("purchases-search").addEventListener("input", filterPurchases);
document.getElementById("purchases-status-filter").addEventListener("change", filterPurchases);

function filterPurchases() {
    const search = document.getElementById("purchases-search").value.toLowerCase();
    const status = document.getElementById("purchases-status-filter").value;

    let filtered = state.purchaseAssignments;
    if (search) {
        filtered = filtered.filter((a) => {
            const planItem = state.plan[a.plan_index] || {};
            return (planItem.url || "").toLowerCase().includes(search) ||
                   (planItem.recommended_anchor || "").toLowerCase().includes(search) ||
                   (a.assigned_site || "").toLowerCase().includes(search);
        });
    }
    if (status === "matched") filtered = filtered.filter((a) => !!a.assigned_site);
    if (status === "not_matched") filtered = filtered.filter((a) => !a.assigned_site);

    renderPurchasesTable(filtered);
}

// Export purchases
document.getElementById("btn-export-purchases").addEventListener("click", () => {
    window.open(`${API_BASE}/projects/${projectId}/export`, "_blank");
});

// ==================== Replace Site Modal ====================

let replaceState = {
    planIndex: null,
    allSites: [],
};

async function openReplaceSiteModal(planIndex) {
    replaceState.planIndex = planIndex;
    const planItem = state.plan[planIndex] || {};
    const current = state.purchaseAssignments.find((a) => a.plan_index === planIndex);

    // Context info
    document.getElementById("replace-context").innerHTML =
        `<strong>URL:</strong> ${shortenUrl(planItem.url || "")} &nbsp;|&nbsp; ` +
        `<strong>Анкор:</strong> ${planItem.recommended_anchor || "—"} &nbsp;|&nbsp; ` +
        `<strong>Тип:</strong> ${formatAnchorType(planItem.anchor_type || "")}`;

    // Current site info
    if (current && current.assigned_site) {
        const short = current.assigned_site.replace(/^https?:\/\//, "").replace(/\/$/, "");
        document.getElementById("replace-current").innerHTML =
            `<span class="label">Поточна площадка:</span> ` +
            `<strong>${short}</strong> &nbsp;|&nbsp; DR: ${current.site_dr ?? "—"} &nbsp;|&nbsp; ` +
            `Трафік: ${current.site_organic != null ? Number(current.site_organic).toLocaleString() : "—"} &nbsp;|&nbsp; ` +
            `Ціна: ${Number(current.site_price).toLocaleString()} ₴ &nbsp;|&nbsp; ` +
            `Якість: ${current.site_quality}`;
        document.getElementById("replace-current").style.display = "flex";
    } else {
        document.getElementById("replace-current").innerHTML =
            `<span class="label">Поточна площадка:</span> <em>Не підібрано</em>`;
        document.getElementById("replace-current").style.display = "flex";
    }

    // Budget hint for price filter
    const budget = state.settings?.monthly_budget || 0;
    const totalRows = state.plan.length || 1;
    const avgBudget = budget > 0 ? Math.round(budget / totalRows) : 0;
    document.getElementById("replace-max-price").value = avgBudget > 0 ? avgBudget * 2 : "";

    document.getElementById("replace-search").value = "";
    document.getElementById("replace-site-modal").style.display = "flex";

    // Collect domains already used by OTHER rows
    const excludeDomains = [];
    for (const a of state.purchaseAssignments) {
        if (a.plan_index !== planIndex && a.assigned_site) {
            const dk = a.assigned_site.replace(/^https?:\/\//, "").replace(/\/$/, "").toLowerCase();
            excludeDomains.push(dk);
        }
    }

    // Fetch available sites
    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/available-sites`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ exclude_domains: excludeDomains }),
        });
        const data = await resp.json();
        if (resp.ok) {
            replaceState.allSites = data.sites;
            renderReplaceSitesTable();
        }
    } catch (err) {
        console.error("Failed to load available sites:", err);
    }
}

function renderReplaceSitesTable() {
    const search = document.getElementById("replace-search").value.toLowerCase();
    const maxPrice = parseFloat(document.getElementById("replace-max-price").value) || Infinity;

    let sites = replaceState.allSites;
    if (search) {
        sites = sites.filter((s) =>
            (s.domain || "").toLowerCase().includes(search) ||
            (s.theme || "").toLowerCase().includes(search)
        );
    }
    if (maxPrice < Infinity) {
        sites = sites.filter((s) => (s.price || 0) <= maxPrice);
    }

    const tbody = document.querySelector("#replace-sites-table tbody");
    if (!sites.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text-muted)">Нічого не знайдено</td></tr>';
        return;
    }

    tbody.innerHTML = sites.slice(0, 150).map((s) => {
        const short = (s.domain || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
        const q = s.quality || 0;
        const cls = q >= 70 ? "quality-high" : (q >= 40 ? "quality-mid" : "quality-low");
        return `
        <tr>
            <td>${s.url ? `<a href="${s.url}" target="_blank" class="site-domain-link">${short}</a>` : short}</td>
            <td>${s.dr ?? "—"}</td>
            <td>${s.organic != null ? Number(s.organic).toLocaleString() : "—"}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${s.theme || ""}">${s.theme || "—"}</td>
            <td>${s.age ?? "—"}</td>
            <td>${Number(s.price || 0).toLocaleString()} ₴</td>
            <td><div class="quality-bar"><div class="quality-bar-fill"><span class="${cls}" style="width:${q}%"></span></div><span>${q}</span></div></td>
            <td><button class="btn-choose-site" data-domain-key="${s.domain_key}" data-domain="${s.domain}" data-url="${s.url || ""}" data-dr="${s.dr ?? ""}" data-traffic="${s.traffic ?? ""}" data-organic="${s.organic ?? ""}" data-price="${s.price || 0}" data-quality="${q}" data-theme="${s.theme || ""}">Обрати</button></td>
        </tr>`;
    }).join("");

    tbody.querySelectorAll(".btn-choose-site").forEach((btn) => {
        btn.addEventListener("click", () => {
            applySiteReplacement({
                assigned_site: btn.dataset.domain,
                site_url: btn.dataset.url,
                site_dr: btn.dataset.dr ? parseFloat(btn.dataset.dr) : null,
                site_traffic: btn.dataset.traffic ? parseFloat(btn.dataset.traffic) : null,
                site_organic: btn.dataset.organic ? parseFloat(btn.dataset.organic) : null,
                site_price: parseFloat(btn.dataset.price) || 0,
                site_quality: parseFloat(btn.dataset.quality) || 0,
                site_theme: btn.dataset.theme,
            });
        });
    });
}

function applySiteReplacement(siteData) {
    const idx = replaceState.planIndex;
    const aIdx = state.purchaseAssignments.findIndex((a) => a.plan_index === idx);
    if (aIdx === -1) return;

    const oldPrice = state.purchaseAssignments[aIdx].site_price || 0;
    const newPrice = siteData.site_price || 0;

    state.purchaseAssignments[aIdx] = {
        plan_index: idx,
        ...siteData,
    };

    // Recalculate stats
    if (state.purchaseStats) {
        const wasMatched = oldPrice > 0 || state.purchaseAssignments[aIdx].assigned_site;
        state.purchaseStats.total_cost = state.purchaseStats.total_cost - oldPrice + newPrice;

        const matched = state.purchaseAssignments.filter((a) => !!a.assigned_site).length;
        state.purchaseStats.matched = matched;
        state.purchaseStats.not_matched = state.purchaseStats.total_plan - matched;

        const budget = state.settings?.monthly_budget || 0;
        if (budget > 0) {
            state.purchaseStats.remaining_budget = Math.round((budget - state.purchaseStats.total_cost) * 100) / 100;
        }
    }

    renderPurchases();
    closeReplaceSiteModal();
}

// Manual site entry
document.getElementById("replace-manual-btn").addEventListener("click", () => {
    const domain = document.getElementById("replace-manual-domain").value.trim();
    const price = parseFloat(document.getElementById("replace-manual-price").value) || 0;
    if (!domain) { alert("Введіть домен"); return; }

    applySiteReplacement({
        assigned_site: domain,
        site_url: null,
        site_dr: null,
        site_traffic: null,
        site_organic: null,
        site_price: price,
        site_quality: 0,
        site_theme: "",
        is_manual: true,
    });
});

// Close modal
function closeReplaceSiteModal() {
    document.getElementById("replace-site-modal").style.display = "none";
    replaceState.planIndex = null;
    replaceState.allSites = [];
}

document.getElementById("replace-modal-close").addEventListener("click", closeReplaceSiteModal);
document.getElementById("replace-site-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("replace-site-modal")) closeReplaceSiteModal();
});

// Live filters in modal
document.getElementById("replace-search").addEventListener("input", renderReplaceSitesTable);
document.getElementById("replace-max-price").addEventListener("input", renderReplaceSitesTable);

// ========== Statistics Section ==========

const STAT_TYPE_COLORS = {
    exact_match: "rgba(108,92,231,0.8)",
    partial_match: "rgba(0,184,148,0.8)",
    branded: "rgba(253,203,110,0.8)",
    url: "rgba(116,185,255,0.8)",
    generic: "rgba(136,136,170,0.6)",
    other: "rgba(100,100,120,0.5)",
};

const STAT_TYPE_LABELS = {
    exact_match: "Exact Match",
    partial_match: "Partial Match",
    branded: "Branded",
    url: "URL",
    generic: "Generic",
    other: "Other",
};

let statCharts = {};

function parseBrandNames(brandName) {
    if (!brandName || typeof brandName !== "string") return [];
    return brandName.split(",").map(b => b.trim()).filter(Boolean);
}

function classifyAnchorJS(anchorText, targetKeywords, brandName, targetUrl) {
    const text = (anchorText || "").toLowerCase().trim();
    if (!text || text === "[image]" || text === "[no anchor text]") return "generic";
    if (/^https?:\/\/\S+$/.test(text) || /^www\.\S+$/.test(text)) return "url";
    const brands = parseBrandNames(brandName);
    for (const b of brands) { if (b && text.includes(b.toLowerCase())) return "branded"; }

    const kwList = (targetKeywords || []).map(k => k.toLowerCase().trim());
    for (const kw of kwList) {
        if (text === kw) return "exact_match";
        if (kw.includes(text) || text.includes(kw)) return "partial_match";
    }

    const kwWords = new Set();
    kwList.forEach(kw => kw.split(/\s+/).forEach(w => kwWords.add(w)));
    const textWords = new Set(text.split(/\s+/));
    let overlap = 0;
    for (const w of textWords) { if (kwWords.has(w)) overlap++; }
    if (overlap >= 2) return "partial_match";

    const genericAnchors = new Set([
        "тут","тут.","сюди","далі","детальніше","дізнатися більше",
        "перейти","на сайті","на сайт","посилання","click here",
        "here","read more","learn more","this","link","website",
        "visit","source","click","check","view","see more",
    ]);
    if (genericAnchors.has(text)) return "generic";

    return "other";
}

function collectStatData() {
    const brandName = state.settings?.brand_name || "";
    const allBacklinks = [];

    for (const page of state.analysis) {
        const rawAnchors = page.raw_anchors || [];
        const keywords = (page.keywords || []).map(kw => kw.keyword);
        for (const bl of rawAnchors) {
            allBacklinks.push({
                target_url: bl.target_url || page.url,
                anchor: bl.anchor || "",
                referring_url: bl.referring_url || "",
                dr: bl.dr,
                traffic: bl.traffic,
                placement_date: bl.placement_date || null,
                cost: parseFloat(bl.cost) || 0,
                type: classifyAnchorJS(bl.anchor, keywords, brandName, page.url),
            });
        }
    }
    return allBacklinks;
}

function hasStatData() {
    const all = collectStatData();
    return all.length > 0;
}

function hasDateData() {
    const all = collectStatData();
    return all.some(bl => parseStatDate(bl.placement_date) !== null);
}

const UA_MONTHS = {
    "січня": "01", "лютого": "02", "березня": "03", "квітня": "04",
    "травня": "05", "червня": "06", "липня": "07", "серпня": "08",
    "вересня": "09", "жовтня": "10", "листопада": "11", "грудня": "12",
    "січень": "01", "лютий": "02", "березень": "03", "квітень": "04",
    "травень": "05", "червень": "06", "липень": "07", "серпень": "08",
    "вересень": "09", "жовтень": "10", "листопад": "11", "грудень": "12",
};

function parseStatDate(dateStr) {
    if (!dateStr) return null;
    const s = String(dateStr).trim();
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return new Date(s.substring(0, 10));
    if (/^\d{2}\.\d{2}\.\d{4}/.test(s)) {
        const [d, m, y] = s.split(".");
        return new Date(`${y}-${m}-${d}`);
    }
    const uaMatch = s.match(/^(\d{1,2})\s+(\S+)\s+(\d{4})$/);
    if (uaMatch) {
        const monthNum = UA_MONTHS[uaMatch[2].toLowerCase()];
        if (monthNum) {
            return new Date(`${uaMatch[3]}-${monthNum}-${uaMatch[1].padStart(2, "0")}`);
        }
    }
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
}

function toMonthKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    return `${y}-${m}`;
}

function renderStatistics() {
    const navStat = document.getElementById("nav-statistics");
    const emptyState = document.getElementById("stat-empty-state");
    const statContent = document.getElementById("stat-content");

    const hasData = hasStatData();
    const hasAnalysis = state.analysis && state.analysis.length > 0;

    navStat.style.display = hasAnalysis ? "" : "none";
    navStat.classList.remove("disabled");

    if (!hasData) {
        if (emptyState) emptyState.style.display = "block";
        if (statContent) statContent.style.display = "none";
        return;
    }

    if (emptyState) emptyState.style.display = "none";
    if (statContent) statContent.style.display = "block";

    const hasDates = hasDateData();
    const filterBar = document.getElementById("stat-date-filter-bar");
    if (filterBar) filterBar.style.display = hasDates ? "flex" : "none";
    const compareRow = document.getElementById("stat-compare-row");
    if (compareRow) compareRow.style.display = hasDates ? "block" : "none";

    if (hasDates) {
        const allBl = collectStatData();
        const dates = allBl.map(bl => parseStatDate(bl.placement_date)).filter(Boolean);
        dates.sort((a, b) => a - b);

        const fromInput = document.getElementById("stat-date-from");
        const toInput = document.getElementById("stat-date-to");
        if (!fromInput.value && dates.length) fromInput.value = dates[0].toISOString().substring(0, 10);
        if (!toInput.value && dates.length) toInput.value = dates[dates.length - 1].toISOString().substring(0, 10);
    }

    bindStatQuickDates();
    applyStatFilter();
}

let statFilteredData = [];
let statSort = { column: "count", direction: "desc" };
let statPage = 0;
const STAT_PAGE_SIZE = 15;

function applyStatFilter() {
    const fromVal = document.getElementById("stat-date-from")?.value;
    const toVal = document.getElementById("stat-date-to")?.value;
    const from = fromVal ? new Date(fromVal) : null;
    const to = toVal ? new Date(toVal + "T23:59:59") : null;
    const typeFilter = document.getElementById("stat-type-filter")?.value || "";
    const costMin = parseFloat(document.getElementById("stat-cost-min")?.value) || null;
    const costMax = parseFloat(document.getElementById("stat-cost-max")?.value) || null;

    const allBl = collectStatData();
    const hasDates = hasDateData();

    let filtered = allBl;

    if (hasDates && (from || to)) {
        filtered = filtered.filter(bl => {
            const d = parseStatDate(bl.placement_date);
            if (!d) return false;
            if (from && d < from) return false;
            if (to && d > to) return false;
            return true;
        });
    }

    if (typeFilter) filtered = filtered.filter(bl => bl.type === typeFilter);
    if (costMin != null) filtered = filtered.filter(bl => bl.cost >= costMin);
    if (costMax != null) filtered = filtered.filter(bl => bl.cost <= costMax);

    statFilteredData = filtered;

    const compareMode = document.getElementById("stat-compare-mode")?.checked;
    if (compareMode && hasDates && from && to) {
        const periodMs = to - from;
        const prevTo = new Date(from.getTime() - 1);
        const prevFrom = new Date(prevTo.getTime() - periodMs);
        let prevFiltered = allBl.filter(bl => {
            const d = parseStatDate(bl.placement_date);
            if (!d) return false;
            return d >= prevFrom && d <= prevTo;
        });
        if (typeFilter) prevFiltered = prevFiltered.filter(bl => bl.type === typeFilter);
        if (costMin != null) prevFiltered = prevFiltered.filter(bl => bl.cost >= costMin);
        if (costMax != null) prevFiltered = prevFiltered.filter(bl => bl.cost <= costMax);
        renderStatComparison(filtered, prevFiltered);
    } else {
        document.getElementById("stat-comparison-block").style.display = "none";
    }

    renderStatSummary(filtered);
    if (hasDates) {
        document.getElementById("stat-chart-dynamics").parentElement.style.display = "";
        document.getElementById("stat-chart-types-stacked").parentElement.parentElement.style.display = "";
        renderStatDynamicsChart(filtered);
        renderStatTypesStackedChart(filtered);
    } else {
        document.getElementById("stat-chart-dynamics").parentElement.style.display = "none";
        document.getElementById("stat-chart-types-stacked").parentElement.parentElement.style.display = "none";
    }
    renderStatTypesPieChart(filtered);
    statPage = 0;
    renderStatUrlTable(filtered);
}

function bindStatQuickDates() {
    document.querySelectorAll(".stat-quick-date").forEach((btn) => {
        btn.onclick = () => {
            const now = new Date();
            const preset = btn.dataset.preset;
            let from, to;
            if (preset === "month") {
                from = new Date(now.getFullYear(), now.getMonth(), 1);
                to = new Date(now);
            } else if (preset === "3months") {
                from = new Date(now.getFullYear(), now.getMonth() - 2, 1);
                to = new Date(now);
            } else if (preset === "year") {
                from = new Date(now.getFullYear(), 0, 1);
                to = new Date(now);
            }
            if (from) document.getElementById("stat-date-from").value = from.toISOString().substring(0, 10);
            if (to) document.getElementById("stat-date-to").value = to.toISOString().substring(0, 10);
            applyStatFilter();
        };
    });
}

function renderStatComparison(current, previous) {
    const block = document.getElementById("stat-comparison-block");
    if (!block) return;
    const currLinks = current.length;
    const prevLinks = previous.length;
    const currCost = current.reduce((s, b) => s + b.cost, 0);
    const prevCost = previous.reduce((s, b) => s + b.cost, 0);
    const linksDiff = prevLinks ? ((currLinks - prevLinks) / prevLinks * 100).toFixed(1) : "—";
    const costDiff = prevCost ? ((currCost - prevCost) / prevCost * 100).toFixed(1) : "—";
    const curr = state.settings?.currency || "UAH";
    block.style.display = "block";
    block.innerHTML = `
        <h4><i class="fas fa-balance-scale"></i> Порівняння з попереднім періодом</h4>
        <div class="stat-comparison-grid">
            <div><span>Посилань:</span> ${currLinks} <span class="stat-diff ${currLinks >= prevLinks ? "positive" : "negative"}">(${linksDiff}%)</span></div>
            <div><span>Витрати:</span> ${Math.round(currCost).toLocaleString("uk-UA")} ${curr} <span class="stat-diff ${currCost >= prevCost ? "positive" : "negative"}">(${costDiff}%)</span></div>
        </div>
    `;
}

function getStatCurrency() {
    return state.settings?.currency || "UAH";
}

const STAT_CARD_TOOLTIPS = {
    total: "Загальна кількість закуплених посилань у вибраному періоді",
    cost: "Сума вартості всіх посилань",
    avg: "Середня вартість одного посилання",
    donors: "Кількість унікальних сайтів-донорів (referring_url)",
    urls: "Кількість цільових сторінок, на які куплені посилання",
};

function renderStatSummary(data) {
    const totalLinks = data.length;
    const totalCost = data.reduce((s, b) => s + b.cost, 0);
    const avgCost = totalLinks > 0 ? totalCost / totalLinks : 0;
    const uniqueDonors = new Set(data.map(b => b.referring_url).filter(Boolean)).size;
    const uniqueUrls = new Set(data.map(b => b.target_url).filter(Boolean)).size;
    const curr = getStatCurrency();

    document.getElementById("stat-summary-row").innerHTML = `
        <div class="stat-card total with-tooltip" title="${STAT_CARD_TOOLTIPS.total}"><div class="stat-value">${totalLinks}</div><div class="stat-label">Всього посилань</div></div>
        <div class="stat-card with-tooltip" title="${STAT_CARD_TOOLTIPS.cost}"><div class="stat-value">${Math.round(totalCost).toLocaleString("uk-UA")} ${curr}</div><div class="stat-label">Витрачено</div></div>
        <div class="stat-card with-tooltip" title="${STAT_CARD_TOOLTIPS.avg}"><div class="stat-value">${Math.round(avgCost).toLocaleString("uk-UA")} ${curr}</div><div class="stat-label">Середня вартість</div></div>
        <div class="stat-card with-tooltip" title="${STAT_CARD_TOOLTIPS.donors}"><div class="stat-value">${uniqueDonors}</div><div class="stat-label">Унікальних донорів</div></div>
        <div class="stat-card with-tooltip" title="${STAT_CARD_TOOLTIPS.urls}"><div class="stat-value">${uniqueUrls}</div><div class="stat-label">Цільових URL</div></div>
    `;
}

function renderStatDynamicsChart(data) {
    const byMonth = {};
    for (const bl of data) {
        const d = parseStatDate(bl.placement_date);
        if (!d) continue;
        const key = toMonthKey(d);
        if (!byMonth[key]) byMonth[key] = { count: 0, cost: 0 };
        byMonth[key].count++;
        byMonth[key].cost += bl.cost;
    }

    const labels = Object.keys(byMonth).sort();
    const counts = labels.map(k => byMonth[k].count);
    const costs = labels.map(k => Math.round(byMonth[k].cost));

    if (statCharts.dynamics) statCharts.dynamics.destroy();
    const ctx = document.getElementById("stat-chart-dynamics").getContext("2d");
    statCharts.dynamics = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [
                {
                    label: "Посилань",
                    data: counts,
                    backgroundColor: "rgba(108,92,231,0.7)",
                    borderRadius: 4,
                    yAxisID: "y",
                },
                {
                    label: `Витрати (${getStatCurrency()})`,
                    data: costs,
                    type: "line",
                    borderColor: "rgba(253,203,110,0.9)",
                    backgroundColor: "rgba(253,203,110,0.1)",
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    yAxisID: "y1",
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: { mode: "index", intersect: false },
            plugins: { legend: { labels: { color: "#8888aa" } } },
            scales: {
                x: { ticks: { color: "#8888aa" }, grid: { color: "rgba(42,42,74,0.5)" } },
                y: { position: "left", ticks: { color: "#8888aa" }, grid: { color: "rgba(42,42,74,0.5)" }, title: { display: true, text: "Посилань", color: "#8888aa" } },
                y1: { position: "right", ticks: { color: "#fdcb6e" }, grid: { drawOnChartArea: false }, title: { display: true, text: getStatCurrency(), color: "#fdcb6e" } },
            },
        },
    });
}

function renderStatTypesPieChart(data) {
    const typeCounts = {};
    for (const bl of data) {
        typeCounts[bl.type] = (typeCounts[bl.type] || 0) + 1;
    }

    const types = Object.keys(typeCounts).sort();
    const values = types.map(t => typeCounts[t]);
    const colors = types.map(t => STAT_TYPE_COLORS[t] || "rgba(100,100,120,0.5)");
    const labels = types.map(t => STAT_TYPE_LABELS[t] || t);

    if (statCharts.typesPie) statCharts.typesPie.destroy();
    const ctx = document.getElementById("stat-chart-types-pie").getContext("2d");
    statCharts.typesPie = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels,
            datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { position: "right", labels: { color: "#8888aa", padding: 12, font: { size: 12 } } },
            },
        },
    });
}

function renderStatTypesStackedChart(data) {
    const byMonth = {};
    const allTypes = new Set();
    for (const bl of data) {
        const d = parseStatDate(bl.placement_date);
        if (!d) continue;
        const key = toMonthKey(d);
        if (!byMonth[key]) byMonth[key] = {};
        byMonth[key][bl.type] = (byMonth[key][bl.type] || 0) + 1;
        allTypes.add(bl.type);
    }

    const labels = Object.keys(byMonth).sort();
    const typeArr = Array.from(allTypes).sort();

    const datasets = typeArr.map(type => ({
        label: STAT_TYPE_LABELS[type] || type,
        data: labels.map(month => byMonth[month][type] || 0),
        backgroundColor: STAT_TYPE_COLORS[type] || "rgba(100,100,120,0.5)",
        borderRadius: 2,
    }));

    if (statCharts.typesStacked) statCharts.typesStacked.destroy();
    const ctx = document.getElementById("stat-chart-types-stacked").getContext("2d");
    statCharts.typesStacked = new Chart(ctx, {
        type: "bar",
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { labels: { color: "#8888aa" } } },
            scales: {
                x: { stacked: true, ticks: { color: "#8888aa" }, grid: { color: "rgba(42,42,74,0.5)" } },
                y: { stacked: true, ticks: { color: "#8888aa" }, grid: { color: "rgba(42,42,74,0.5)" } },
            },
        },
    });
}

function renderStatUrlTable(data) {
    const searchTerm = (document.getElementById("stat-url-search")?.value || "").toLowerCase();
    const curr = getStatCurrency();

    const byUrl = {};
    for (const bl of data) {
        const url = bl.target_url;
        if (!byUrl[url]) byUrl[url] = { url, backlinks: [], cost: 0, types: new Set() };
        byUrl[url].backlinks.push(bl);
        byUrl[url].cost += bl.cost;
        byUrl[url].types.add(bl.type);
    }

    let rows = Object.values(byUrl);
    if (searchTerm) rows = rows.filter(r => r.url.toLowerCase().includes(searchTerm));

    const col = statSort.column;
    const dir = statSort.direction === "asc" ? 1 : -1;
    rows.sort((a, b) => {
        let va, vb;
        if (col === "url") { va = a.url; vb = b.url; return dir * String(va).localeCompare(vb); }
        if (col === "count") { va = a.backlinks.length; vb = b.backlinks.length; return dir * (va - vb); }
        if (col === "cost") { va = a.cost; vb = b.cost; return dir * (va - vb); }
        return 0;
    });

    const totalRows = rows.length;
    const totalPages = Math.ceil(totalRows / STAT_PAGE_SIZE) || 1;
    statPage = Math.min(statPage, totalPages - 1);
    const pageRows = rows.slice(statPage * STAT_PAGE_SIZE, (statPage + 1) * STAT_PAGE_SIZE);

    const tbody = document.querySelector("#stat-url-table tbody");
    tbody.innerHTML = "";

    document.querySelectorAll("#stat-url-table th.sortable").forEach((th) => {
        th.classList.remove("sorted-asc", "sorted-desc");
        if (th.dataset.sort === col) th.classList.add(statSort.direction === "asc" ? "sorted-asc" : "sorted-desc");
    });

    for (let i = 0; i < pageRows.length; i++) {
        const actualIdx = statPage * STAT_PAGE_SIZE + i;
        const r = pageRows[i];
        const typeBadges = Array.from(r.types).map(t =>
            `<span class="stat-type-badge ${t}" title="${STAT_TYPE_LABELS[t] || t}">${STAT_TYPE_LABELS[t] || t}</span>`
        ).join("");

        const mainRow = document.createElement("tr");
        mainRow.className = "stat-url-row";
        mainRow.dataset.idx = actualIdx;
        mainRow.innerHTML = `
            <td><i class="fas fa-chevron-right stat-url-toggle" data-idx="${actualIdx}"></i></td>
            <td title="${escapeTitle(r.url)}" style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.url}</td>
            <td>${r.backlinks.length}</td>
            <td>${Math.round(r.cost).toLocaleString("uk-UA")} ${curr}</td>
            <td><div class="stat-type-badges">${typeBadges}</div></td>
        `;

        const detailRow = document.createElement("tr");
        detailRow.className = "stat-url-detail";
        detailRow.id = `stat-detail-${actualIdx}`;
        const detailTd = document.createElement("td");
        detailTd.colSpan = 5;
        detailTd.innerHTML = buildUrlDetailHTML(r, actualIdx);
        detailRow.appendChild(detailTd);

        tbody.appendChild(mainRow);
        tbody.appendChild(detailRow);

        mainRow.addEventListener("click", () => toggleStatDetail(actualIdx));
    }

    document.querySelectorAll("#stat-url-table th.sortable").forEach((th) => {
        th.onclick = () => {
            const c = th.dataset.sort;
            if (statSort.column === c) statSort.direction = statSort.direction === "asc" ? "desc" : "asc";
            else { statSort.column = c; statSort.direction = "desc"; }
            renderStatUrlTable(statFilteredData);
        };
    });

    const pagEl = document.getElementById("stat-pagination");
    if (totalRows > STAT_PAGE_SIZE) {
        pagEl.style.display = "flex";
        pagEl.innerHTML = `
            <button class="btn btn-sm btn-outline" ${statPage === 0 ? "disabled" : ""} id="stat-prev">← Назад</button>
            <span class="stat-page-info">Сторінка ${statPage + 1} з ${totalPages} (${totalRows} URL)</span>
            <button class="btn btn-sm btn-outline" ${statPage >= totalPages - 1 ? "disabled" : ""} id="stat-next">Далі →</button>
        `;
        document.getElementById("stat-prev")?.addEventListener("click", () => { statPage--; renderStatUrlTable(statFilteredData); });
        document.getElementById("stat-next")?.addEventListener("click", () => { statPage++; renderStatUrlTable(statFilteredData); });
    } else {
        pagEl.style.display = "none";
    }
}

function buildUrlDetailHTML(urlData, idx) {
    const blSorted = [...urlData.backlinks].sort((a, b) => {
        const da = parseStatDate(a.placement_date);
        const db = parseStatDate(b.placement_date);
        if (!da || !db) return 0;
        return db - da;
    });

    let anchorsHTML = blSorted.map(bl => `
        <tr>
            <td>${bl.anchor}</td>
            <td><span class="stat-type-badge ${bl.type}">${STAT_TYPE_LABELS[bl.type] || bl.type}</span></td>
            <td title="${bl.referring_url}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${bl.referring_url || "—"}</td>
            <td>${bl.dr != null ? bl.dr : "—"}</td>
            <td>${bl.placement_date || "—"}</td>
            <td>${bl.cost ? Math.round(bl.cost).toLocaleString("uk-UA") + " " + getStatCurrency() : "—"}</td>
        </tr>
    `).join("");

    return `
        <div class="stat-url-detail-inner">
            <h4>Закуплені анкори</h4>
            <table class="stat-anchor-table">
                <thead><tr><th>Анкор</th><th>Тип</th><th>Донор</th><th>DR</th><th>Дата</th><th>Вартість</th></tr></thead>
                <tbody>${anchorsHTML}</tbody>
            </table>
            <div class="stat-detail-charts">
                <div class="stat-detail-chart-box">
                    <h5>Динаміка закупок</h5>
                    <canvas id="stat-url-dynamics-${idx}" height="150"></canvas>
                </div>
                <div class="stat-detail-chart-box">
                    <h5>Розподіл анкорів</h5>
                    <canvas id="stat-url-pie-${idx}" height="150"></canvas>
                </div>
            </div>
        </div>
    `;
}

const statDetailCharts = {};

function toggleStatDetail(idx) {
    const detail = document.getElementById(`stat-detail-${idx}`);
    const toggle = document.querySelector(`.stat-url-toggle[data-idx="${idx}"]`);
    if (!detail || !toggle) return;

    const isOpen = detail.classList.contains("open");
    if (isOpen) {
        detail.classList.remove("open");
        toggle.classList.remove("open");
        if (statDetailCharts[idx]) {
            statDetailCharts[idx].forEach(c => c.destroy());
            delete statDetailCharts[idx];
        }
        return;
    }

    detail.classList.add("open");
    toggle.classList.add("open");

    const allBl = collectStatData();
    const fromVal = document.getElementById("stat-date-from").value;
    const toVal = document.getElementById("stat-date-to").value;
    const from = fromVal ? new Date(fromVal) : null;
    const to = toVal ? new Date(toVal + "T23:59:59") : null;
    const hasDates = hasDateData();

    const mainRow = detail.previousElementSibling;
    const url = mainRow.querySelector("td:nth-child(2)").getAttribute("title");

    const urlBl = allBl.filter(bl => {
        if (bl.target_url !== url) return false;
        if (hasDates && (from || to)) {
            const d = parseStatDate(bl.placement_date);
            if (!d) return false;
            if (from && d < from) return false;
            if (to && d > to) return false;
        }
        return true;
    });

    const charts = [];

    // Mini dynamics bar (only if date data available)
    const dynCanvas = document.getElementById(`stat-url-dynamics-${idx}`);
    if (dynCanvas && hasDates) {
        const byMonth = {};
        for (const bl of urlBl) {
            const d = parseStatDate(bl.placement_date);
            if (!d) continue;
            const key = toMonthKey(d);
            byMonth[key] = (byMonth[key] || 0) + 1;
        }
        const mLabels = Object.keys(byMonth).sort();
        const mCounts = mLabels.map(k => byMonth[k]);

        if (mLabels.length > 0) {
            const c = new Chart(dynCanvas.getContext("2d"), {
                type: "bar",
                data: {
                    labels: mLabels,
                    datasets: [{ data: mCounts, backgroundColor: "rgba(108,92,231,0.7)", borderRadius: 3 }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: "#8888aa", font: { size: 10 } }, grid: { display: false } },
                        y: { ticks: { color: "#8888aa", font: { size: 10 } }, grid: { color: "rgba(42,42,74,0.3)" } },
                    },
                },
            });
            charts.push(c);
        }
    } else if (dynCanvas) {
        dynCanvas.parentElement.style.display = "none";
    }

    // Mini types pie
    const typeCounts = {};
    for (const bl of urlBl) {
        typeCounts[bl.type] = (typeCounts[bl.type] || 0) + 1;
    }
    const pTypes = Object.keys(typeCounts).sort();
    const pVals = pTypes.map(t => typeCounts[t]);
    const pColors = pTypes.map(t => STAT_TYPE_COLORS[t] || "rgba(100,100,120,0.5)");
    const pLabels = pTypes.map(t => STAT_TYPE_LABELS[t] || t);

    const pieCanvas = document.getElementById(`stat-url-pie-${idx}`);
    if (pieCanvas) {
        const c = new Chart(pieCanvas.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: pLabels,
                datasets: [{ data: pVals, backgroundColor: pColors, borderWidth: 0 }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "right", labels: { color: "#8888aa", font: { size: 10 }, padding: 6 } },
                },
            },
        });
        charts.push(c);
    }

    statDetailCharts[idx] = charts;
}

// Event listeners for statistics
document.getElementById("stat-apply-filter")?.addEventListener("click", applyStatFilter);
document.getElementById("stat-reset-filter")?.addEventListener("click", () => {
    document.getElementById("stat-date-from").value = "";
    document.getElementById("stat-date-to").value = "";
    document.getElementById("stat-type-filter").value = "";
    document.getElementById("stat-cost-min").value = "";
    document.getElementById("stat-cost-max").value = "";
    document.getElementById("stat-compare-mode").checked = false;
    renderStatistics();
});
document.getElementById("stat-url-search")?.addEventListener("input", () => applyStatFilter());
document.getElementById("stat-type-filter")?.addEventListener("change", () => applyStatFilter());
document.getElementById("stat-cost-min")?.addEventListener("input", () => applyStatFilter());
document.getElementById("stat-cost-max")?.addEventListener("input", () => applyStatFilter());
document.getElementById("stat-compare-mode")?.addEventListener("change", () => applyStatFilter());

document.getElementById("stat-export-csv")?.addEventListener("click", () => {
    const rows = statFilteredData;
    const byUrl = {};
    for (const bl of rows) {
        const url = bl.target_url;
        if (!byUrl[url]) byUrl[url] = { url, backlinks: [], cost: 0, types: new Set() };
        byUrl[url].backlinks.push(bl);
        byUrl[url].cost += bl.cost;
        byUrl[url].types.add(bl.type);
    }
    const curr = getStatCurrency();
    const csvRows = [["URL", "Посилань", "Витрачено (" + curr + ")", "Типи анкорів"]];
    Object.values(byUrl).sort((a, b) => b.backlinks.length - a.backlinks.length).forEach(r => {
        csvRows.push([r.url, r.backlinks.length, Math.round(r.cost), Array.from(r.types).join(", ")]);
    });
    const csv = "\ufeff" + csvRows.map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `statistics-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
});

document.getElementById("stat-export-summary")?.addEventListener("click", () => {
    const data = statFilteredData;
    const totalLinks = data.length;
    const totalCost = data.reduce((s, b) => s + b.cost, 0);
    const avgCost = totalLinks > 0 ? totalCost / totalLinks : 0;
    const uniqueDonors = new Set(data.map(b => b.referring_url).filter(Boolean)).size;
    const uniqueUrls = new Set(data.map(b => b.target_url).filter(Boolean)).size;
    const curr = getStatCurrency();
    const fromVal = document.getElementById("stat-date-from")?.value || "—";
    const toVal = document.getElementById("stat-date-to")?.value || "—";
    const txt = `Зведення статистики закупок\nПеріод: ${fromVal} — ${toVal}\n\nВсього посилань: ${totalLinks}\nВитрачено: ${Math.round(totalCost).toLocaleString("uk-UA")} ${curr}\nСередня вартість: ${Math.round(avgCost).toLocaleString("uk-UA")} ${curr}\nУнікальних донорів: ${uniqueDonors}\nЦільових URL: ${uniqueUrls}`;
    const blob = new Blob(["\ufeff" + txt], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `statistics-summary-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
});
