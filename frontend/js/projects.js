const API_BASE = "/api";

let deletingProjectId = null;

loadProjects();

async function loadProjects() {
    try {
        const resp = await fetch(`${API_BASE}/projects`);
        const data = await resp.json();
        renderProjects(data.projects);
    } catch (err) {
        document.getElementById("projects-loader").innerHTML =
            `<i class="fas fa-exclamation-triangle" style="color:var(--danger)"></i> Не вдалося з'єднатися з сервером`;
    }
}

function renderProjects(projects) {
    const grid = document.getElementById("projects-grid");
    const empty = document.getElementById("projects-empty");

    if (!projects.length) {
        grid.style.display = "none";
        empty.style.display = "block";
        return;
    }

    empty.style.display = "none";
    grid.style.display = "grid";

    grid.innerHTML = projects
        .map(
            (p) => `
        <div class="project-card" data-id="${p.id}">
            <div class="project-card-header">
                <span class="project-card-name">${escapeHtml(p.name)}</span>
                <div class="project-card-actions">
                    <button class="btn-icon delete-project-btn" data-id="${p.id}" data-name="${escapeHtml(p.name)}" title="Видалити">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            </div>
            ${p.domain ? `<div class="project-card-domain"><i class="fas fa-globe"></i> ${escapeHtml(p.domain)}</div>` : ""}
            ${p.brand_name ? `<div class="project-card-brand"><i class="fas fa-tag"></i> ${escapeHtml(p.brand_name)}</div>` : ""}
            <div class="project-card-stats">
                <span class="stat"><i class="fas fa-file-alt"></i> ${p.pages_count} сторінок</span>
                <span class="stat"><i class="fas fa-link"></i> ${p.plan_count} анкорів</span>
            </div>
            <div class="project-card-date">
                Оновлено: ${formatDate(p.updated_at)}
            </div>
        </div>
    `
        )
        .join("");

    grid.querySelectorAll(".project-card").forEach((card) => {
        card.addEventListener("click", (e) => {
            if (e.target.closest(".delete-project-btn")) return;
            window.location.href = `project.html?id=${card.dataset.id}`;
        });
    });

    grid.querySelectorAll(".delete-project-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            deletingProjectId = btn.dataset.id;
            document.getElementById("del-confirm-text").textContent =
                `Видалити проект "${btn.dataset.name}"? Цю дію неможливо скасувати.`;
            document.getElementById("delete-modal").style.display = "flex";
        });
    });
}

// --- New Project Modal ---
document.getElementById("new-project-btn").addEventListener("click", () => {
    document.getElementById("np-name").value = "";
    document.getElementById("np-domain").value = "";
    document.getElementById("np-brand").value = "";
    document.getElementById("new-project-modal").style.display = "flex";
    document.getElementById("np-name").focus();
});

document.getElementById("np-modal-close").addEventListener("click", () => closeModal("new-project-modal"));
document.getElementById("np-modal-cancel").addEventListener("click", () => closeModal("new-project-modal"));
document.getElementById("new-project-modal").addEventListener("click", (e) => {
    if (e.target.id === "new-project-modal") closeModal("new-project-modal");
});

document.getElementById("np-modal-create").addEventListener("click", async () => {
    const name = document.getElementById("np-name").value.trim();
    const domain = document.getElementById("np-domain").value.trim();
    const brand = document.getElementById("np-brand").value.trim();

    if (!name) {
        document.getElementById("np-name").focus();
        return;
    }

    const btn = document.getElementById("np-modal-create");
    btn.disabled = true;
    btn.textContent = "Створюємо...";

    try {
        const resp = await fetch(`${API_BASE}/projects`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, domain, brand_name: brand }),
        });
        const data = await resp.json();
        if (resp.ok) {
            window.location.href = `project.html?id=${data.id}`;
        } else {
            alert(data.error || "Помилка");
        }
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Створити";
    }
});

// --- Delete Modal ---
document.getElementById("del-modal-close").addEventListener("click", () => closeModal("delete-modal"));
document.getElementById("del-modal-cancel").addEventListener("click", () => closeModal("delete-modal"));
document.getElementById("delete-modal").addEventListener("click", (e) => {
    if (e.target.id === "delete-modal") closeModal("delete-modal");
});

document.getElementById("del-modal-confirm").addEventListener("click", async () => {
    if (!deletingProjectId) return;

    const btn = document.getElementById("del-modal-confirm");
    btn.disabled = true;
    btn.textContent = "Видаляємо...";

    try {
        await fetch(`${API_BASE}/projects/${deletingProjectId}`, { method: "DELETE" });
        closeModal("delete-modal");
        loadProjects();
    } catch (err) {
        alert("Помилка: " + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Видалити";
        deletingProjectId = null;
    }
});

// --- Helpers ---
function closeModal(id) {
    document.getElementById(id).style.display = "none";
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(iso) {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        return d.toLocaleDateString("uk-UA", {
            day: "numeric",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return iso;
    }
}
