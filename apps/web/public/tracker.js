// ============================================================================
// NAVI SCHEME — Application Tracker (Connected to SQLite Database & API)
// ============================================================================

const STATUS_LABEL = {
  saved: "Saved to Apply",
  applied: "Applied on Official Portal",
  under_review: "Under Verification / Review",
  disbursed: "Benefit Approved / Disbursed",
  rejected: "Rejected / Ineligible",
};

const STATUS_STEPS = ["saved", "applied", "under_review", "disbursed"];

function statusIndex(status) {
  const idx = STATUS_STEPS.indexOf(status);
  return idx >= 0 ? idx : 0;
}

let loadedApplications = [];
let activeFilter = "all";

function renderStats(list) {
  const counts = {
    total: list.length,
    saved: list.filter((i) => (i.status || "saved") === "saved").length,
    applied: list.filter((i) => i.status === "applied" || i.status === "under_review").length,
    disbursed: list.filter((i) => i.status === "disbursed").length,
  };

  const container = document.getElementById("trackerStats");
  if (!container) return;

  container.innerHTML = `
    <article class="mini-stat"><strong>${counts.total}</strong><span>In your list</span></article>
    <article class="mini-stat"><strong>${counts.saved}</strong><span>Saved to apply</span></article>
    <article class="mini-stat"><strong>${counts.applied}</strong><span>In progress</span></article>
    <article class="mini-stat"><strong>${counts.disbursed}</strong><span>Disbursed</span></article>
  `;
}

function renderCard(app) {
  const currentStep = app.status || "saved";
  const currIdx = statusIndex(currentStep);

  const stepsHtml = STATUS_STEPS.map((step, i) => {
    const state = i < currIdx ? "done" : i === currIdx ? "now" : "";
    return `<li class="${state}"><span></span>${STATUS_LABEL[step] || step}</li>`;
  }).join("");

  const title = app.title || app.name || "Government Scheme";
  const category = app.category || app.sector || "WELFARE";
  const ref = app.reference_no || app.ref || `NS-${String(app.id || app.scheme_id).substring(0, 8).toUpperCase()}`;
  const notes = app.notes || app.description || "Track your document submissions and status updates directly.";
  const amount = app.benefits || app.amount || "Official welfare benefit";
  const portal = app.application_url || app.portal || "https://www.india.gov.in";
  const savedDate = app.created_at ? new Date(app.created_at).toLocaleDateString() : (app.savedAt || "Recently");
  const updatedDate = app.updated_at ? new Date(app.updated_at).toLocaleDateString() : (app.updatedAt || "Recently");
  const schemeId = app.scheme_id || app.id;

  return `
    <article class="track-card" data-scheme-id="${schemeId}">
      <div class="card-top">
        <div class="card-meta">
          <span class="cat-tag">${category.toUpperCase()}</span>
          <span class="loc-tag">${ref}</span>
        </div>
        <span class="eligible" style="font-weight:700;">${STATUS_LABEL[currentStep] || currentStep}</span>
      </div>
      <h3>${title}</h3>
      <p class="scheme-desc">${notes}</p>
      <p class="track-amount" style="font-weight:700;color:#047857;margin:8px 0;">${amount}</p>
      <ol class="timeline">${stepsHtml}</ol>

      <div style="margin: 14px 0 10px; display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <label style="font-size:12px; font-weight:700; color:#475569;">UPDATE STATUS:</label>
        <select class="status-updater-select" data-scheme-id="${schemeId}" style="padding:6px 10px; border-radius:6px; border:1px solid #cbd5e1; font-size:12.5px; font-weight:600;">
          <option value="saved" ${currentStep === "saved" ? "selected" : ""}>1. Saved to Apply</option>
          <option value="applied" ${currentStep === "applied" ? "selected" : ""}>2. Applied on Official Portal</option>
          <option value="under_review" ${currentStep === "under_review" ? "selected" : ""}>3. Under Verification</option>
          <option value="disbursed" ${currentStep === "disbursed" ? "selected" : ""}>4. Benefit Disbursed</option>
        </select>
        <button type="button" class="btn btn-ghost btn-remove-saved" data-scheme-id="${schemeId}" style="margin-left:auto; color:#ef4444; padding:5px 10px; font-size:12px;">
          ✕ Remove
        </button>
      </div>

      <div class="card-actions">
        <a class="btn btn-apply" href="${portal}" target="_blank" rel="noopener">Open official portal</a>
        <a class="btn btn-ai" href="assistant.html?q=${encodeURIComponent("Explain " + title)}">Explain with AI</a>
      </div>
      <div class="card-footer">
        <span class="footer-link">Added: ${savedDate}</span>
        <span class="footer-link">Updated: ${updatedDate}</span>
      </div>
    </article>`;
}

async function loadTrackerData() {
  const mount = document.getElementById("trackerList");
  if (!mount) return;

  mount.innerHTML = `
    <div style="padding:40px; text-align:center; color:#64748b;">
      <div class="spinner" style="display:inline-block;width:24px;height:24px;border:3px solid #cbd5e1;border-top-color:#2563eb;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
      <p style="margin-top:12px; font-weight:600;">Loading your tracked applications…</p>
    </div>
  `;

  try {
    if (isLoggedIn()) {
      // Authenticated citizen: fetch from backend SQLite database
      const [savedSchemes, apps] = await Promise.all([
        API.getSavedSchemes().catch(() => []),
        API.getApplications().catch(() => []),
      ]);

      const statusMap = new Map();
      apps.forEach((a) => {
        statusMap.set(a.scheme_id, a);
      });

      loadedApplications = savedSchemes.map((s) => {
        const appState = statusMap.get(s.id) || {};
        return {
          ...s,
          scheme_id: s.id,
          status: appState.status || "saved",
          notes: appState.notes || s.description || "Saved scheme",
          updated_at: appState.updated_at || s.created_at,
        };
      });
    } else {
      // Guest mode: load local saved items
      const localIds = getLocalSavedApps();
      if (localIds.length > 0) {
        // Fetch details from backend for these IDs
        const items = await Promise.all(
          localIds.map(async (item) => {
            const id = typeof item === "string" ? item : item.id;
            try {
              const details = await API.getScheme(id);
              return {
                ...details,
                scheme_id: details.id,
                status: typeof item === "object" && item.status ? item.status : "saved",
                savedAt: typeof item === "object" && item.savedAt ? item.savedAt : new Date().toLocaleDateString(),
              };
            } catch {
              return typeof item === "object" ? item : { id, title: id, status: "saved" };
            }
          })
        );
        loadedApplications = items.filter(Boolean);
      } else {
        loadedApplications = [];
      }
    }
  } catch (err) {
    console.error("Tracker load error:", err);
    loadedApplications = [];
  }

  paint(activeFilter);
}

function paint(filter) {
  activeFilter = filter;
  const mount = document.getElementById("trackerList");
  if (!mount) return;

  const list =
    filter === "all"
      ? loadedApplications
      : loadedApplications.filter((item) => (item.status || "saved") === filter);

  renderStats(loadedApplications);

  if (!list.length) {
    mount.innerHTML = `
      <div class="empty-state" style="background:#fff; border-radius:12px; padding:48px 24px; text-align:center; border:1px solid #e2e8f0;">
        <h3 style="font-size:18px; color:#1e293b; margin-bottom:8px;">No schemes in this status lane</h3>
        <p style="color:#64748b; margin-bottom:16px;">
          ${!isLoggedIn()
        ? "Sign in to save and manage your applications securely, or discover schemes to bookmark."
        : "Discover welfare schemes matching your criteria and save them to track your application journey."
      }
        </p>
        <div style="display:flex; justify-content:center; gap:12px;">
          <a class="btn btn-signin" href="index.html">Discover Schemes</a>
          ${!isLoggedIn() ? `<a class="btn btn-evaluate" href="login.html">Sign In to Sync</a>` : ""}
        </div>
      </div>`;
    return;
  }

  mount.innerHTML = list.map(renderCard).join("");
}

// Handle status change
async function handleStatusChange(schemeId, newStatus) {
  try {
    if (isLoggedIn()) {
      await API.updateApplicationStatus(schemeId, newStatus, `Status updated to ${STATUS_LABEL[newStatus]}`);
    } else {
      const list = getLocalSavedApps();
      const idx = list.findIndex((i) => (typeof i === "string" ? i === schemeId : i.id === schemeId));
      if (idx >= 0) {
        if (typeof list[idx] === "string") {
          list[idx] = { id: schemeId, status: newStatus, updatedAt: new Date().toISOString() };
        } else {
          list[idx].status = newStatus;
          list[idx].updatedAt = new Date().toISOString();
        }
        writeJSON(STORAGE_KEYS.LOCAL_SAVED_APPS, list);
      }
    }

    const item = loadedApplications.find((a) => (a.scheme_id || a.id) === schemeId);
    if (item) {
      item.status = newStatus;
      item.updated_at = new Date().toISOString();
    }

    paint(activeFilter);
    showToast(`Application status updated to "${STATUS_LABEL[newStatus] || newStatus}"`, "success");
  } catch (err) {
    console.error("Failed to update status:", err);
    showToast("Could not update application status. Please retry.", "error");
  }
}

// Handle removal
async function handleRemoveScheme(schemeId) {
  try {
    if (isLoggedIn()) {
      await API.removeSavedScheme(schemeId);
    }
    toggleLocalSaved(schemeId);

    loadedApplications = loadedApplications.filter((a) => (a.scheme_id || a.id) !== schemeId);
    paint(activeFilter);
    showToast("Scheme removed from your tracker", "info");
  } catch (err) {
    console.error("Failed to remove scheme:", err);
    showToast("Could not remove scheme. Please retry.", "error");
  }
}

function initTracker() {
  loadTrackerData();

  // Filter tab buttons
  const filterWrap = document.getElementById("statusFilters");
  if (filterWrap) {
    filterWrap.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter]");
      if (!btn) return;
      document.querySelectorAll("#statusFilters .seg-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      paint(btn.getAttribute("data-filter"));
    });
  }

  // Delegation for status select and remove button
  const listWrap = document.getElementById("trackerList");
  if (listWrap) {
    listWrap.addEventListener("change", (e) => {
      const sel = e.target.closest(".status-updater-select");
      if (sel) {
        const schemeId = sel.getAttribute("data-scheme-id");
        handleStatusChange(schemeId, sel.value);
      }
    });

    listWrap.addEventListener("click", (e) => {
      const rmBtn = e.target.closest(".btn-remove-saved");
      if (rmBtn) {
        e.preventDefault();
        const schemeId = rmBtn.getAttribute("data-scheme-id");
        if (confirm("Remove this scheme from your scheme tracker?")) {
          handleRemoveScheme(schemeId);
        }
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", initTracker);
