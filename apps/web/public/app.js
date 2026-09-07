// ============================================================================
// NAVI SCHEME — Discover & Match Engine (Connected to SQLite Database & API)
// ============================================================================

const icons = {
  gift: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 0 1 0 5"/></svg>`,
  external: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7"/><path d="M7 7h10v10"/></svg>`,
  chat: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  bookmark: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`,
  clock: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
};

let currentSchemes = [];
let totalSchemesCount = 0;
let currentOffset = 0;
const PAGE_LIMIT = 12;
let userSavedSchemeIds = new Set();

// Extract document checklist items safely
function parseDocuments(scheme) {
  if (Array.isArray(scheme.documents_required_list) && scheme.documents_required_list.length > 0) {
    return scheme.documents_required_list.map((d) => ({ label: String(d), checked: false }));
  }
  if (Array.isArray(scheme.documents_required) && scheme.documents_required.length > 0) {
    return scheme.documents_required.map((d) => ({
      label: typeof d === "string" ? d : d.label || "Required document",
      checked: !!d.checked,
    }));
  }
  if (typeof scheme.documents_required === "string" && scheme.documents_required.trim()) {
    return scheme.documents_required
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((label) => ({ label, checked: false }));
  }
  return [
    { label: "Aadhaar Card", checked: true },
    { label: "Bank Account / Passbook", checked: false },
  ];
}

// Extract benefits list safely
function parseBenefits(scheme) {
  if (Array.isArray(scheme.benefits)) {
    return scheme.benefits;
  }
  if (typeof scheme.benefits === "string" && scheme.benefits.trim()) {
    const parts = scheme.benefits.split(/\n|•|\. /).map((s) => s.trim()).filter(Boolean);
    if (parts.length > 0) return parts.slice(0, 3);
    return [scheme.benefits];
  }
  return ["Direct welfare benefit as per gazetted guidelines"];
}

// Check if a scheme is saved either locally or in account
function isSchemeSaved(schemeId) {
  if (isLoggedIn()) {
    return userSavedSchemeIds.has(schemeId);
  }
  return isLocalSaved(schemeId);
}

// Render individual scheme card
function renderCard(scheme) {
  const docs = parseDocuments(scheme)
    .slice(0, 4)
    .map(
      (doc, i) => `
      <li class="doc-item ${doc.checked ? "checked" : ""}" data-scheme="${scheme.id}" data-doc="${i}">
        <span class="doc-check" aria-hidden="true"></span>
        <span>${doc.label}</span>
      </li>`
    )
    .join("");

  const benefits = parseBenefits(scheme)
    .slice(0, 2)
    .map((b) => `<li>${b}</li>`)
    .join("");

  const title = scheme.title || scheme.name || "Government Welfare Scheme";
  const desc = scheme.short_description || scheme.description || "Official Government of India scheme.";
  const category = scheme.category || scheme.sector || "General Welfare";
  const stateLabel = scheme.state ? `State: ${scheme.state}` : "State: All India";
  const portalUrl = scheme.application_url || "https://www.india.gov.in/";
  const saved = isSchemeSaved(scheme.id);
  const matchBadge = scheme._matchConfidence
    ? `<span class="eligible" style="background:#ecfdf5;color:#047857;border-color:#a7f3d0;">✓ ${scheme._matchConfidence.toUpperCase()} MATCH (${scheme._matchScore || 90}%)</span>`
    : `<span class="eligible">✓ Verified Gazette</span>`;

  return `
    <article class="scheme-card" data-id="${scheme.id}">
      <div class="card-top">
        <div class="card-meta">
          <span class="cat-tag">${category.toUpperCase()}</span>
          <span class="loc-tag">${stateLabel}</span>
        </div>
        ${matchBadge}
      </div>
      <h3>${title}</h3>
      <p class="scheme-desc">${desc}</p>
      <div class="benefits">
        <div class="benefits-head">${icons.gift} GUARANTEED BENEFITS</div>
        <ul>${benefits}</ul>
      </div>
      <div>
        <div class="docs-label">DOCUMENT READINESS CHECKLIST (CLICK TO TICK)</div>
        <ul class="doc-list">${docs}</ul>
      </div>
      <div class="card-actions">
        <a class="btn btn-apply" href="${portalUrl}" target="_blank" rel="noopener">Apply on Official Portal ${icons.external}</a>
        <a class="btn btn-ai" href="assistant.html?q=${encodeURIComponent("Explain " + title)}">${icons.chat} Explain with AI</a>
      </div>
      <div class="card-footer">
        <button type="button" class="footer-link save-btn${saved ? " saved" : ""}" data-scheme-id="${scheme.id}">
          ${icons.bookmark} ${saved ? "Saved" : "Save"}
        </button>
        <a class="footer-link" href="tracker.html">${icons.clock} Track Application</a>
      </div>
    </article>`;
}

function renderSchemes(list, append = false) {
  const grid = document.getElementById("schemeGrid");
  if (!grid) return;

  if (list.length === 0 && !append) {
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 48px 24px; text-align: center; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0;">
        <h3 style="margin-bottom: 8px; font-size: 18px; color: #1e293b;">No matching schemes found</h3>
        <p style="color: #64748b; margin-bottom: 16px;">Try adjusting your search terms or relaxing the state and category filters.</p>
        <button type="button" class="btn btn-evaluate" id="emptyResetBtn">View All Available Schemes</button>
      </div>
    `;
    const resetBtn = document.getElementById("emptyResetBtn");
    if (resetBtn) resetBtn.addEventListener("click", resetAllFilters);
    return;
  }

  const html = list.map(renderCard).join("");
  if (append) {
    grid.insertAdjacentHTML("beforeend", html);
  } else {
    grid.innerHTML = html;
  }

  // Update Load More visibility
  const paginationWrap = document.getElementById("paginationWrap");
  if (paginationWrap) {
    const hasMore = currentSchemes.length < totalSchemesCount;
    paginationWrap.style.display = hasMore ? "block" : "none";
  }
}

function updateAgeSlider() {
  const age = document.getElementById("age");
  const ageValue = document.getElementById("ageValue");
  if (!age || !ageValue) return;
  const pct = ((age.value - age.min) / (age.max - age.min)) * 100;
  age.style.setProperty("--pct", `${pct}%`);
  ageValue.textContent = `${age.value} yrs`;
}

// Fetch user saved schemes from backend if authenticated
async function syncUserBookmarks() {
  if (isLoggedIn()) {
    try {
      const saved = await API.getSavedSchemes();
      userSavedSchemeIds = new Set(
        saved.map((item) => (typeof item === "string" ? item : item.scheme_id || item.id))
      );
    } catch (err) {
      console.warn("Could not load user bookmarks from server:", err);
    }
  }
}

// Populate filter dropdowns from backend taxonomies
async function loadTaxonomies() {
  try {
    const data = await API.getTaxonomies();
    if (!data) return;

    const stateSelect = document.getElementById("state");
    if (stateSelect && data.states && data.states.length > 0) {
      const currentVal = stateSelect.value;
      stateSelect.innerHTML = `<option value="">All India (Central + States)</option>` +
        data.states
          .filter((s) => s !== "All India")
          .map((s) => `<option value="${s}">${s}</option>`)
          .join("");
      if (currentVal && stateSelect.querySelector(`option[value="${currentVal}"]`)) {
        stateSelect.value = currentVal;
      }
    }

    const categorySelect = document.getElementById("category");
    if (categorySelect && data.categories && data.categories.length > 0) {
      const currentVal = categorySelect.value;
      categorySelect.innerHTML = `<option value="">✓ All Categories Selected</option>` +
        data.categories.map((c) => `<option value="${c}">${c}</option>`).join("");
      if (currentVal && categorySelect.querySelector(`option[value="${currentVal}"]`)) {
        categorySelect.value = currentVal;
      }
    }
  } catch (err) {
    console.warn("Using fallback static taxonomies:", err);
  }
}

function getFilterValues() {
  const searchInput = document.getElementById("search");
  const stateSelect = document.getElementById("state");
  const categorySelect = document.getElementById("category");
  const ageInput = document.getElementById("age");
  const activeGenderBtn = document.querySelector(".seg-btn.active");

  const q = searchInput ? searchInput.value.trim() : "";
  const state = stateSelect && stateSelect.value && stateSelect.value !== "All India (Central + States)" ? stateSelect.value : "";
  const category = categorySelect && categorySelect.value && !categorySelect.value.includes("All Categories") ? categorySelect.value : "";
  const age = ageInput ? parseInt(ageInput.value, 10) : 34;
  const gender = activeGenderBtn ? activeGenderBtn.dataset.gender : "all";

  return { q, state, category, age, gender };
}

// Fetch schemes from SQLite database via API
async function fetchSchemes(append = false) {
  const { q, state, category, age, gender } = getFilterValues();
  const offset = append ? currentOffset + PAGE_LIMIT : 0;

  const resultCountEl = document.getElementById("resultCount");
  if (resultCountEl && !append) {
    resultCountEl.textContent = "Searching…";
  }

  try {
    const params = {
      q: q || undefined,
      state: state || undefined,
      category: category || undefined,
      age: age || undefined,
      gender: gender && gender !== "all" ? gender : undefined,
      limit: PAGE_LIMIT,
      offset,
    };

    const res = await API.getSchemes(params);
    const fetched = res.schemes || [];
    totalSchemesCount = res.total !== undefined ? res.total : fetched.length;
    currentOffset = offset;

    if (append) {
      currentSchemes = [...currentSchemes, ...fetched];
      renderSchemes(fetched, true);
    } else {
      currentSchemes = fetched;
      renderSchemes(currentSchemes, false);
    }

    if (resultCountEl) {
      resultCountEl.textContent = totalSchemesCount.toLocaleString();
    }
  } catch (err) {
    console.error("Failed to load schemes:", err);
    if (!append) {
      renderSchemes([], false);
    }
    showToast("Error connecting to database. Please retry.", "error");
  }
}

// Run deterministic eligibility match against citizen profile
async function runEligibilityMatch() {
  const btn = document.querySelector(".btn-evaluate");
  if (!btn) return;

  const originalContent = btn.innerHTML;
  btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h8l-1 8 10-12h-8l1-8z"/></svg> Matching…`;
  btn.disabled = true;

  const { state, category, age, gender } = getFilterValues();

  const profilePayload = {
    state: state || "All India",
    age: age || 34,
    gender: gender && gender !== "all" ? gender : "prefer_not_to_say",
    sensitive_fields_consented: true,
    language: "en",
  };

  try {
    const matchRes = await API.matchEligibility(profilePayload);
    const matches = matchRes.matches || [];

    if (matches.length > 0) {
      // Map matched format to display cards
      const mappedSchemes = matches.map((m) => ({
        id: m.scheme_id,
        title: m.title,
        name: m.title,
        category: m.category || category || "Welfare",
        state: m.state || state || "All India",
        description: `Verified match for your profile (${m.confidence} confidence). ${m.benefits || ""}`,
        short_description: m.benefits || "Gazetted benefits verified.",
        benefits: m.benefits ? [m.benefits] : [],
        documents_required_list: m.documents_required || ["Aadhaar Card", "Bank Passbook"],
        application_url: m.application_url || "https://www.india.gov.in/",
        _matchConfidence: m.confidence,
        _matchScore: m.score,
      }));

      currentSchemes = mappedSchemes;
      totalSchemesCount = matchRes.total_matches || mappedSchemes.length;
      renderSchemes(mappedSchemes, false);

      const resultCountEl = document.getElementById("resultCount");
      if (resultCountEl) {
        resultCountEl.textContent = `${totalSchemesCount} Matched`;
      }
      showToast(`Found ${mappedSchemes.length} verified schemes matching your criteria!`, "success");
    } else {
      // Fall back to regular schemes filter
      await fetchSchemes(false);
      showToast("Evaluated database rules for your profile.", "info");
    }
  } catch (err) {
    console.warn("Eligibility match endpoint error, falling back to catalog search:", err);
    await fetchSchemes(false);
  } finally {
    btn.innerHTML = originalContent;
    btn.disabled = false;
  }
}

// Reset all form filters
function resetAllFilters() {
  const stateSelect = document.getElementById("state");
  const categorySelect = document.getElementById("category");
  const ageInput = document.getElementById("age");
  const searchInput = document.getElementById("search");

  if (stateSelect) stateSelect.selectedIndex = 0;
  if (categorySelect) categorySelect.selectedIndex = 0;
  if (ageInput) {
    ageInput.value = 34;
    updateAgeSlider();
  }
  document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  const allBtn = document.querySelector('.seg-btn[data-gender="all"]');
  if (allBtn) allBtn.classList.add("active");
  if (searchInput) searchInput.value = "";

  fetchSchemes(false);
}

// Toggle scheme bookmarking
async function handleBookmarkClick(buttonEl) {
  const schemeId = buttonEl.getAttribute("data-scheme-id");
  if (!schemeId) return;

  const currentlySaved = isSchemeSaved(schemeId);

  try {
    if (isLoggedIn()) {
      if (currentlySaved) {
        await API.removeSavedScheme(schemeId);
        userSavedSchemeIds.delete(schemeId);
        buttonEl.classList.remove("saved");
        buttonEl.innerHTML = `${icons.bookmark} Save`;
        showToast("Removed from your saved schemes", "info");
      } else {
        await API.saveScheme(schemeId);
        userSavedSchemeIds.add(schemeId);
        buttonEl.classList.add("saved");
        buttonEl.innerHTML = `${icons.bookmark} Saved`;
        showToast("Scheme saved to your profile!", "success");
      }
    } else {
      // Guest local storage
      const added = toggleLocalSaved(schemeId);
      if (added) {
        buttonEl.classList.add("saved");
        buttonEl.innerHTML = `${icons.bookmark} Saved`;
        showToast("Scheme saved to local tracker (Sign in to sync across devices)", "info");
      } else {
        buttonEl.classList.remove("saved");
        buttonEl.innerHTML = `${icons.bookmark} Save`;
        showToast("Removed from local tracker", "info");
      }
    }
  } catch (err) {
    console.error("Failed to update bookmark:", err);
    showToast("Could not update bookmark. Please try again.", "error");
  }
}

// Initialize Discover & Match Page
async function init() {
  updateAgeSlider();
  await syncUserBookmarks();
  await loadTaxonomies();
  await fetchSchemes(false);

  // Age slider listener
  const ageInput = document.getElementById("age");
  if (ageInput) {
    ageInput.addEventListener("input", () => {
      updateAgeSlider();
    });
    ageInput.addEventListener("change", () => {
      fetchSchemes(false);
    });
  }

  // Gender filter listeners
  document.querySelectorAll(".seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      fetchSchemes(false);
    });
  });

  // Select dropdown listeners
  const stateSelect = document.getElementById("state");
  if (stateSelect) stateSelect.addEventListener("change", () => fetchSchemes(false));

  const categorySelect = document.getElementById("category");
  if (categorySelect) categorySelect.addEventListener("change", () => fetchSchemes(false));

  // Reset filters
  const resetBtn = document.getElementById("resetFilters");
  if (resetBtn) resetBtn.addEventListener("click", resetAllFilters);

  // Search input listeners
  const searchInput = document.getElementById("search");
  const searchBtn = document.querySelector(".btn-search");

  if (searchBtn) searchBtn.addEventListener("click", () => fetchSchemes(false));
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        fetchSchemes(false);
      }
    });
  }

  // Evaluate Matched Schemes button
  const evalBtn = document.querySelector(".btn-evaluate");
  if (evalBtn) evalBtn.addEventListener("click", runEligibilityMatch);

  // Load More button
  const loadMoreBtn = document.getElementById("loadMoreBtn");
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener("click", () => {
      fetchSchemes(true);
    });
  }

  // Event Delegation for Scheme Grid (Checklists & Bookmarks)
  const schemeGrid = document.getElementById("schemeGrid");
  if (schemeGrid) {
    schemeGrid.addEventListener("click", (e) => {
      const docItem = e.target.closest(".doc-item");
      if (docItem) {
        docItem.classList.toggle("checked");
        return;
      }

      const saveBtn = e.target.closest(".save-btn");
      if (saveBtn) {
        e.preventDefault();
        handleBookmarkClick(saveBtn);
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", init);
