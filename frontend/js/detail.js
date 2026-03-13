const API_BASE = (typeof window !== "undefined" && window.location.port === "5000") ? "/api" : "http://localhost:5000/api";

const params = new URLSearchParams(window.location.search);
const projectId = params.get("project");
const targetUrl = params.get("url");

let detailData = null;
let currentSort = { field: "count", dir: "desc" };

const backLink = document.querySelector("#back-link a");
if (backLink && projectId) {
    backLink.href = `project.html?id=${projectId}`;
}

if (!projectId || !targetUrl) {
    document.getElementById("detail-loader").innerHTML =
        '<i class="fas fa-exclamation-triangle" style="color:var(--danger)"></i> Не вказано project або url параметр.';
} else {
    loadDetail();
}

async function loadDetail() {
    try {
        const resp = await fetch(`${API_BASE}/projects/${projectId}/url-detail`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: targetUrl }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            document.getElementById("detail-loader").innerHTML =
                `<i class="fas fa-exclamation-triangle" style="color:var(--danger)"></i> ${data.error || "Помилка"}`;
            return;
        }

        detailData = data;
        document.getElementById("detail-loader").style.display = "none";
        document.getElementById("detail-content").style.display = "block";
        renderAll();
    } catch (err) {
        document.getElementById("detail-loader").innerHTML =
            `<i class="fas fa-exclamation-triangle" style="color:var(--danger)"></i> Помилка з'єднання: ${err.message}`;
    }
}

function renderAll() {
    renderHeader();
    renderStats();
    renderAnchorsTable(detailData.anchors_grouped);
    renderDistribution();
    renderKeywords();
    renderRecommendations();
    initTabs();
    initAnchorsFilters();
    initSorting();
}

// --- Header ---
function renderHeader() {
    document.title = `${shortenUrl(detailData.url)} — Anchor Plan`;
    document.getElementById("detail-url").textContent = detailData.url;
    document.getElementById("detail-external-link").href = detailData.url;

    document.getElementById("detail-badges").innerHTML = `
        <span class="badge badge-${detailData.priority}">${detailData.priority.toUpperCase()}</span>
        <span style="color:var(--text-muted);font-size:13px">Бал: ${detailData.priority_score}</span>
    `;
}

// --- Stats ---
function renderStats() {
    document.getElementById("detail-stats").innerHTML = `
        <div class="detail-stat">
            <div class="stat-value">${detailData.total_backlinks}</div>
            <div class="stat-label">Беклінки</div>
        </div>
        <div class="detail-stat">
            <div class="stat-value">${detailData.dofollow_count}</div>
            <div class="stat-label">Dofollow</div>
        </div>
        <div class="detail-stat">
            <div class="stat-value">${detailData.nofollow_count}</div>
            <div class="stat-label">Nofollow</div>
        </div>
        <div class="detail-stat">
            <div class="stat-value">${detailData.unique_anchors}</div>
            <div class="stat-label">Унік. анкорів</div>
        </div>
        <div class="detail-stat">
            <div class="stat-value">${detailData.unique_donors}</div>
            <div class="stat-label">Унік. донорів</div>
        </div>
        <div class="detail-stat">
            <div class="stat-value">${detailData.keywords.length}</div>
            <div class="stat-label">Ключових слів</div>
        </div>
    `;
}

function renderSourceBadges(sources) {
    if (!sources || !Array.isArray(sources) || sources.length === 0) return "";
    const labels = { positions: "P", ahrefs: "a", collaborator: "K" };
    return sources.map((s) => `<span class="source-badge badge-${s}" title="${s === "positions" ? "Реєстр позицій" : s === "ahrefs" ? "Ahrefs" : "Collaborator"}">${labels[s] || s}</span>`).join("");
}

// --- Anchors Table ---
function renderAnchorsTable(data) {
    const tbody = document.querySelector("#anchors-table tbody");
    tbody.innerHTML = data
        .map(
            (a, i) => {
                const volStr = a.volume != null && a.volume > 0 ? Number(a.volume).toLocaleString("uk-UA") : "—";
                const targetKw = a.type === "exact_match" || (a.sources && a.sources.includes("positions")) ? a.anchor : "";
                return `
        <tr>
            <td>${escapeHtml(a.anchor)}${a.sources ? renderSourceBadges(a.sources) : ""}</td>
            <td>${a.count}</td>
            <td><span class="badge badge-${a.type}">${formatAnchorType(a.type)}</span></td>
            <td>${a.avg_dr !== null ? a.avg_dr : "—"}</td>
            <td>${volStr}</td>
            <td>${a.dofollow}</td>
            <td>${a.nofollow}</td>
            <td>
                <span class="donors-toggle" data-donors="${i}">${a.donors.length} донор(ів)</span>
                <div class="donors-list" id="donors-${i}">
                    ${a.donors.map((d) => `<a href="${escapeHtml(ensureUrlProtocol(d))}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(d)}">${shortenUrl(d)}</a>`).join("")}
                </div>
            </td>
            <td><button class="btn-icon btn-add-to-plan" data-anchor="${escapeHtml(a.anchor)}" data-type="${a.type}" data-target="${escapeHtml(targetKw)}" data-volume="${a.volume != null ? a.volume : ""}" title="Додати в анкор-план"><i class="fas fa-plus"></i></button></td>
        </tr>
    `;
            }
        )
        .join("");

    tbody.querySelectorAll(".donors-toggle").forEach((toggle) => {
        toggle.addEventListener("click", () => {
            const list = document.getElementById(`donors-${toggle.dataset.donors}`);
            list.classList.toggle("open");
        });
    });
    tbody.querySelectorAll(".btn-add-to-plan").forEach((btn) => {
        btn.addEventListener("click", (e) => addAnchorToPlan(e.currentTarget));
    });
}

// --- Distribution ---
function renderDistribution() {
    const typeLabels = {
        exact_match: "Exact Match",
        partial_match: "Partial Match",
        branded: "Branded",
        generic: "Generic",
        url: "URL / Naked Link",
    };

    const statusLabels = {
        normal: "В нормі",
        deficit: "Дефіцит",
        oversaturated: "Перенасичено",
    };

    const grid = document.getElementById("distribution-grid");
    grid.innerHTML = detailData.distribution_comparison
        .map((d) => {
            const maxBar = 60;
            const currentWidth = Math.min(d.current_pct, maxBar);
            const targetLeft = (d.target_min / maxBar) * 100;
            const targetWidth = ((d.target_max - d.target_min) / maxBar) * 100;

            return `
            <div class="dist-row">
                <div class="dist-row-header">
                    <span class="dist-row-label">${typeLabels[d.type] || d.type}</span>
                    <span class="dist-status ${d.status}">${statusLabels[d.status]}</span>
                </div>
                <div class="dist-row-values">
                    <span>Зараз: <span class="current">${d.current_pct}%</span></span>
                    <span>Ціль: ${d.target_min}% — ${d.target_max}%</span>
                </div>
                <div class="dist-bar-wrap">
                    <div class="dist-bar-target" style="left:${targetLeft}%;width:${targetWidth}%"></div>
                    <div class="dist-bar-current ${d.status}" style="width:${(currentWidth / maxBar) * 100}%"></div>
                </div>
            </div>
        `;
        })
        .join("");
}

// --- Keywords ---
function renderKeywords() {
    const tbody = document.querySelector("#keywords-table tbody");
    tbody.innerHTML = detailData.keywords
        .map((kw) => {
            const change =
                kw.previous_position && kw.current_position
                    ? kw.previous_position - kw.current_position
                    : null;
            const changeStr =
                change !== null
                    ? change > 0
                        ? `<span class="dynamics-growth">+${change}</span>`
                        : change < 0
                          ? `<span class="dynamics-decline">${change}</span>`
                          : `<span class="dynamics-stable">0</span>`
                    : "—";

            const volStr = kw.volume != null ? Number(kw.volume).toLocaleString("uk-UA") : "—";
            const kwSources = kw.source ? [kw.source] : ["positions"];
            return `
            <tr>
                <td>${escapeHtml(kw.keyword)}${renderSourceBadges(kwSources)}</td>
                <td>${volStr}</td>
                <td>${kw.first_position ?? "—"}</td>
                <td>${kw.previous_position ?? "—"}</td>
                <td><strong>${kw.current_position ?? "—"}</strong></td>
                <td class="dynamics-${kw.dynamics_label}">${getDynamicsIcon(kw.dynamics_label)} ${kw.dynamics_label}</td>
                <td>${changeStr}</td>
                <td><button class="btn-icon btn-add-to-plan" data-anchor="${escapeHtml(kw.keyword)}" data-type="exact_match" data-target="${escapeHtml(kw.keyword)}" data-volume="${kw.volume != null ? kw.volume : ""}" title="Додати в анкор-план"><i class="fas fa-plus"></i></button></td>
            </tr>
        `;
        })
        .join("");
    tbody.querySelectorAll(".btn-add-to-plan").forEach((btn) => {
        btn.addEventListener("click", (e) => addAnchorToPlan(e.currentTarget));
    });
}

// --- Add to Plan ---
async function addAnchorToPlan(btn) {
    const dataset = btn.dataset;
    const url = detailData.url;
    const anchor = dataset.anchor || "";
    const anchorType = dataset.type || "partial_match";
    const targetKeyword = dataset.target || "";
    const volume = dataset.volume ? parseInt(dataset.volume, 10) : undefined;

    if (!anchor) return;

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    try {
        const body = { url, anchor, anchor_type: anchorType };
        if (targetKeyword) body.target_keyword = targetKeyword;
        if (volume != null && !isNaN(volume)) body.volume = volume;

        const resp = await fetch(`${API_BASE}/projects/${projectId}/plan/add`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await resp.json();

        if (resp.status === 409) {
            alert(data.error || "Такий анкор вже є в плані для цього URL");
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-plus"></i>';
            }
            return;
        }

        if (!resp.ok) {
            alert(data.error || "Помилка додавання");
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-plus"></i>';
            }
            return;
        }

        // Оновлюємо рекомендації з відповіді (url і detailData.url вже канонічні)
        if (data.plan) {
            const ourUrl = (detailData.url || "").toLowerCase().trim();
            detailData.recommendations = (data.plan || [])
                .filter((r) => (r.url || "").toLowerCase().trim() === ourUrl)
                .map((r) => ({
                    recommended_anchor: r.recommended_anchor,
                    anchor_type: r.anchor_type,
                    target_keyword: r.target_keyword,
                    volume: r.volume,
                    rationale: r.rationale,
                }));
            renderRecommendations();
        }
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-plus"></i>';
        }
    }
}

// --- Recommendations ---
function renderRecommendations() {
    const tbody = document.querySelector("#recommendations-table tbody");
    if (!detailData.recommendations.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">Немає рекомендацій для цього URL</td></tr>';
        return;
    }
    tbody.innerHTML = detailData.recommendations
        .map(
            (r) => {
                const volStr = r.volume != null ? Number(r.volume).toLocaleString("uk-UA") : "—";
                return `
        <tr>
            <td><strong>${escapeHtml(r.recommended_anchor)}</strong></td>
            <td><span class="badge badge-${r.anchor_type}">${formatAnchorType(r.anchor_type)}</span></td>
            <td>${r.target_keyword || "—"}</td>
            <td>${volStr}</td>
            <td>${r.rationale || r.comment || ""}</td>
        </tr>
    `;
            }
        )
        .join("");
}

// --- Tabs ---
function initTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
            document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
        });
    });
}

// --- Anchors Filters ---
function initAnchorsFilters() {
    document.getElementById("anchors-search").addEventListener("input", filterAnchors);
    document.getElementById("anchors-type-filter").addEventListener("change", filterAnchors);
}

function filterAnchors() {
    const search = document.getElementById("anchors-search").value.toLowerCase();
    const type = document.getElementById("anchors-type-filter").value;

    let filtered = detailData.anchors_grouped;
    if (search) {
        filtered = filtered.filter((a) => a.anchor.toLowerCase().includes(search));
    }
    if (type) {
        filtered = filtered.filter((a) => a.type === type);
    }
    filtered = sortData(filtered);
    renderAnchorsTable(filtered);
}

// --- Sorting ---
function initSorting() {
    document.querySelectorAll(".sortable").forEach((th) => {
        th.addEventListener("click", () => {
            const field = th.dataset.sort;
            if (currentSort.field === field) {
                currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
            } else {
                currentSort.field = field;
                currentSort.dir = "desc";
            }
            filterAnchors();
        });
    });
}

function sortData(data) {
    const { field, dir } = currentSort;
    return [...data].sort((a, b) => {
        let va = a[field];
        let vb = b[field];
        if (typeof va === "string") va = va.toLowerCase();
        if (typeof vb === "string") vb = vb.toLowerCase();
        if (va == null) va = 0;
        if (vb == null) vb = 0;
        if (va < vb) return dir === "asc" ? -1 : 1;
        if (va > vb) return dir === "asc" ? 1 : -1;
        return 0;
    });
}

// --- Helpers ---
function ensureUrlProtocol(url) {
    if (!url || typeof url !== "string") return "#";
    const s = url.trim();
    if (s.startsWith("http://") || s.startsWith("https://")) return s;
    return "https://" + s;
}

function shortenUrl(url) {
    try {
        const u = new URL(ensureUrlProtocol(url));
        const path = u.pathname === "/" ? "" : u.pathname;
        return u.hostname + path;
    } catch {
        return url;
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function formatAnchorType(type) {
    const map = {
        exact_match: "Exact",
        partial_match: "Partial",
        branded: "Brand",
        generic: "Generic",
        url: "URL",
        other: "Інше",
    };
    return map[type] || type;
}

function getDynamicsIcon(label) {
    if (label === "growth") return '<i class="fas fa-arrow-up"></i>';
    if (label === "decline") return '<i class="fas fa-arrow-down"></i>';
    return '<i class="fas fa-minus"></i>';
}
