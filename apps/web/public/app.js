// ============================================================================
// NAVI SCHEME — Discover & Match Engine (Connected to SQLite Database & APIs)
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
let currentPage = 1;
const PAGE_LIMIT = 24;
const savedSchemesSet = new Set();

function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function isSaved(schemeId) {
  return savedSchemesSet.has(String(schemeId));
}

function parseDocumentsList(scheme) {
  if (Array.isArray(scheme.documentsList) && scheme.documentsList.length > 0) {
    return scheme.documentsList.map(d => typeof d === 'string' ? d : d.label || d.name);
  }
  if (Array.isArray(scheme.documents_required_json) && scheme.documents_required_json.length > 0) {
    return scheme.documents_required_json.map(d => typeof d === 'string' ? d : d.name || d.label);
  }
  if (typeof scheme.documentsRaw === 'string' && scheme.documentsRaw.trim()) {
    return scheme.documentsRaw.split(/[,;\n]+/).map(s => s.trim()).filter(Boolean);
  }
  if (typeof scheme.documents_required === 'string' && scheme.documents_required.trim()) {
    return scheme.documents_required.split(/[,;\n]+/).map(s => s.trim()).filter(Boolean);
  }
  return ['Aadhaar Card', 'Identity & Address Proof', 'Bank Account Passbook (Aadhaar linked)'];
}

function renderCard(scheme, matchInfo = null) {
  const schemeId = scheme.id || scheme.slug || 'scheme';
  const title = scheme.title || scheme.name || scheme.scheme_name || 'Government Welfare Scheme';
  const desc = scheme.details || scheme.description || scheme.short_description || 'Verified government welfare scheme.';
  const category = scheme.primaryCategory || (scheme.categories && scheme.categories[0]) || scheme.category || scheme.sector || 'General Welfare';
  const stateLabel = scheme.state ? `State: ${scheme.state}` : (scheme.level || 'All India');
  const portalUrl = scheme.portalUrl || scheme.application_url || 'https://www.india.gov.in';
  const saved = isSaved(schemeId);

  const docs = parseDocumentsList(scheme).slice(0, 3).map((doc, i) => `
    <li class="doc-item" data-scheme="${escapeHTML(schemeId)}" data-doc="${i}">
      <span class="doc-check" aria-hidden="true"></span>
      <span>${escapeHTML(doc)}</span>
    </li>
  `).join('');

  const benefitsSnippet = scheme.benefits ? `
    <div class="benefits">
      <div class="benefits-head">${icons.gift} GUARANTEED BENEFITS</div>
      <p style="font-size: 12px; color: #334155; line-height: 1.4;">${escapeHTML(scheme.benefits.slice(0, 160))}${scheme.benefits.length > 160 ? '...' : ''}</p>
    </div>
  ` : '';

  const matchBadge = matchInfo
    ? `<span class="eligible" style="background: #ecfdf5; color: #047857; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px;">✓ ${matchInfo.matchPercentage}% Match</span>`
    : `<span class="status-badge ${scheme.isExpired ? 'status-expired' : 'status-active'}">${scheme.isExpired ? 'Expired' : 'Active & Open'}</span>`;

  return `
    <article class="scheme-card" data-id="${escapeHTML(schemeId)}">
      <div class="card-top">
        <div class="card-meta">
          <span class="cat-tag">${escapeHTML(category.toUpperCase())}</span>
          <span class="loc-tag">${escapeHTML(stateLabel)}</span>
        </div>
        ${matchBadge}
      </div>
      <h3>${escapeHTML(title)}</h3>
      <p class="scheme-desc">${escapeHTML(desc)}</p>
      ${benefitsSnippet}
      <div>
        <div class="docs-label">DOCUMENT READINESS (CLICK TO TICK)</div>
        <ul class="doc-list">${docs || '<li class="doc-item"><span class="doc-check"></span><span>Identity & Address Proof</span></li>'}</ul>
      </div>
      <div class="card-actions">
        <a class="btn btn-apply" href="${portalUrl}" target="_blank" rel="noopener">Apply on Official Portal ${icons.external}</a>
        <a class="btn btn-ai" href="assistant.html?q=${encodeURIComponent('Explain ' + title + ' eligibility and how to apply step by step')}">${icons.chat} Ask AI Agent</a>
      </div>
      <div class="card-footer">
        <button type="button" class="footer-link save-btn${saved ? " saved" : ""}" data-scheme="${escapeHTML(schemeId)}">${icons.bookmark} ${saved ? "Saved" : "Save"}</button>
        <a class="footer-link" href="assistant.html?q=${encodeURIComponent('What are the exact portal steps for ' + title + '?')}">${icons.clock} Step-by-Step Guide</a>
      </div>
    </article>`;
}

function renderSchemes(list, matchesMap = null, append = false) {
  const grid = document.getElementById("schemeGrid");
  if (!grid) return;

  if (!list || list.length === 0) {
    if (!append) {
      grid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; padding: 48px 24px; text-align: center; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0;">
          <h3 style="margin-bottom: 8px; font-size: 18px; color: #1e293b;">No matching schemes found</h3>
          <p style="color: #64748b; margin-bottom: 16px;">Try adjusting your search terms or selecting All India.</p>
          <button type="button" class="btn btn-evaluate" id="emptyResetBtn" style="display:inline-flex; width:auto; padding:8px 20px;">View All Available Schemes</button>
        </div>
      `;
      const resetBtn = document.getElementById("emptyResetBtn");
      if (resetBtn) resetBtn.addEventListener("click", resetAllFilters);
    }
    return;
  }

  const html = list.map(item => renderCard(item, matchesMap ? matchesMap.get(item.id || item.slug) : null)).join("");
  if (append) {
    grid.insertAdjacentHTML("beforeend", html);
  } else {
    grid.innerHTML = html;
  }

  // Update Load More visibility
  const paginationWrap = document.getElementById("paginationWrap");
  if (paginationWrap) {
    if (currentSchemes.length < totalSchemesCount) {
      paginationWrap.style.display = "block";
    } else {
      paginationWrap.style.display = "none";
    }
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

async function fetchSchemes(query = '', state = 'All', category = 'All', page = 1, append = false) {
  try {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    if (state && state !== 'All' && !state.includes('All India')) params.append('state', state);
    if (category && category !== 'All' && !category.includes('All Categories')) params.append('category', category);
    params.append('page', page);
    params.append('limit', PAGE_LIMIT);

    const res = await fetch(`/api/schemes?${params.toString()}`);
    const data = await res.json();

    const fetched = data.schemes || [];
    totalSchemesCount = data.total || 3411;
    currentPage = page;

    if (append) {
      currentSchemes = [...currentSchemes, ...fetched];
    } else {
      currentSchemes = fetched;
    }

    const countEl = document.getElementById("resultCount");
    if (countEl) countEl.textContent = String(totalSchemesCount);

    renderSchemes(fetched, null, append);
  } catch (err) {
    console.error('Fetch schemes error:', err);
  }
}

async function loadMetadata() {
  try {
    const res = await fetch('/api/meta');
    const data = await res.json();

    const stateSelect = document.getElementById('state');
    if (stateSelect && data.states) {
      stateSelect.innerHTML = `<option selected>All India (Central + States)</option>` +
        data.states.map(s => `<option value="${escapeHTML(s)}">${escapeHTML(s)}</option>`).join('');
    }

    const catSelect = document.getElementById('category');
    if (catSelect && data.categories) {
      catSelect.innerHTML = `<option selected>✓ All Categories Selected</option>` +
        data.categories.map(c => `<option value="${escapeHTML(c)}">${escapeHTML(c)}</option>`).join('');
    }
  } catch (err) {
    console.error('Meta load error:', err);
  }
}

async function evaluateMatches() {
  const btn = document.querySelector(".btn-evaluate");
  if (!btn) return;

  const originalHtml = btn.innerHTML;
  btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h8l-1 8 10-12h-8l1-8z"/></svg> Matching against 3,411 schemes…`;
  btn.disabled = true;

  const stateVal = document.getElementById("state")?.value || 'All India';
  const ageVal = document.getElementById("age")?.value || '34';
  const activeGenderBtn = document.querySelector(".seg-btn.active");
  const genderVal = activeGenderBtn ? activeGenderBtn.dataset.gender : 'all';
  const categoryVal = document.getElementById("category")?.value || 'All';

  try {
    const res = await fetch('/api/schemes/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state: stateVal.includes('All India') ? 'All India' : stateVal,
        age: parseInt(ageVal, 10),
        gender: genderVal,
        category: categoryVal.includes('All Categories') ? '' : categoryVal,
        occupation: categoryVal
      })
    });
    const data = await res.json();
    btn.innerHTML = originalHtml;
    btn.disabled = false;

    if (data.matches && data.matches.length > 0) {
      const matchesMap = new Map();
      const schemesList = data.matches.map(m => {
        matchesMap.set(m.scheme.id || m.scheme.slug, m);
        return m.scheme;
      });

      currentSchemes = schemesList;
      totalSchemesCount = data.totalMatches || schemesList.length;

      const countEl = document.getElementById("resultCount");
      if (countEl) countEl.textContent = String(totalSchemesCount);

      renderSchemes(schemesList, matchesMap, false);
    } else {
      fetchSchemes();
    }
  } catch (err) {
    btn.innerHTML = originalHtml;
    btn.disabled = false;
    fetchSchemes();
  }
}

function resetAllFilters() {
  const stateEl = document.getElementById("state");
  const catEl = document.getElementById("category");
  const ageEl = document.getElementById("age");
  const searchEl = document.getElementById("search");

  if (stateEl) stateEl.selectedIndex = 0;
  if (catEl) catEl.selectedIndex = 0;
  if (ageEl) {
    ageEl.value = 34;
    updateAgeSlider();
  }
  document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  const allGenderBtn = document.querySelector('.seg-btn[data-gender="all"]');
  if (allGenderBtn) allGenderBtn.classList.add("active");
  if (searchEl) searchEl.value = "";

  fetchSchemes('', 'All', 'All', 1, false);
}

function init() {
  loadMetadata();
  fetchSchemes('', 'All', 'All', 1, false);
  updateAgeSlider();

  const ageInput = document.getElementById("age");
  if (ageInput) ageInput.addEventListener("input", updateAgeSlider);

  document.querySelectorAll(".seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });

  const resetBtn = document.getElementById("resetFilters");
  if (resetBtn) resetBtn.addEventListener("click", resetAllFilters);

  const grid = document.getElementById("schemeGrid");
  if (grid) {
    grid.addEventListener("click", (e) => {
      const docItem = e.target.closest(".doc-item");
      if (docItem) {
        docItem.classList.toggle("checked");
        return;
      }
      const saveBtn = e.target.closest(".save-btn");
      if (saveBtn) {
        const id = saveBtn.dataset.scheme;
        if (savedSchemesSet.has(id)) {
          savedSchemesSet.delete(id);
          saveBtn.classList.remove("saved");
          saveBtn.innerHTML = `${icons.bookmark} Save`;
        } else {
          savedSchemesSet.add(id);
          saveBtn.classList.add("saved");
          saveBtn.innerHTML = `${icons.bookmark} Saved`;
        }
      }
    });
  }

  const searchInput = document.getElementById("search");
  const runSearch = () => {
    const q = searchInput ? searchInput.value.trim() : '';
    const state = document.getElementById("state")?.value || 'All';
    const cat = document.getElementById("category")?.value || 'All';
    fetchSchemes(q, state, cat, 1, false);
  };

  const searchBtn = document.querySelector(".btn-search");
  if (searchBtn) searchBtn.addEventListener("click", runSearch);

  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") runSearch();
    });
  }

  const evaluateBtn = document.querySelector(".btn-evaluate");
  if (evaluateBtn) evaluateBtn.addEventListener("click", evaluateMatches);

  const loadMoreBtn = document.getElementById("loadMoreBtn");
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener("click", () => {
      const q = searchInput ? searchInput.value.trim() : '';
      const state = document.getElementById("state")?.value || 'All';
      const cat = document.getElementById("category")?.value || 'All';
      fetchSchemes(q, state, cat, currentPage + 1, true);
    });
  }

  // Check URL query param
  const urlParams = new URLSearchParams(window.location.search);
  const searchParam = urlParams.get('search') || urlParams.get('q');
  if (searchParam && searchInput) {
    searchInput.value = searchParam;
    runSearch();
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}