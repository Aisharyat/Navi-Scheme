// ============================================================================
// NAVI SCHEME — Discover & Match Engine
// ============================================================================

const icons = {
  gift: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 0 1 0 5"/></svg>`,
  external: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7"/><path d="M7 7h10v10"/></svg>`,
  chat: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  bookmark: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`,
  clock: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  info: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
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
  const sId = String(schemeId);
  return savedSchemesSet.has(sId) || (typeof isLocalSaved === 'function' && isLocalSaved(sId));
}

function initSavedState() {
  if (typeof getLocalSavedApps === 'function') {
    const local = getLocalSavedApps();
    local.forEach(item => {
      const id = typeof item === 'string' ? item : (item.id || item.scheme_id);
      if (id) savedSchemesSet.add(String(id));
    });
  }
  if (typeof isLoggedIn === 'function' && isLoggedIn()) {
    API.getSavedSchemes()
      .then(list => {
        if (Array.isArray(list)) {
          list.forEach(item => {
            const id = item.id || item.scheme_id;
            if (id) savedSchemesSet.add(String(id));
          });
          updateAllSaveButtons();
        }
      })
      .catch(() => { });
  }
}

function updateAllSaveButtons() {
  document.querySelectorAll('.save-btn').forEach(btn => {
    const id = btn.dataset.scheme;
    if (isSaved(id)) {
      btn.classList.add('saved');
      btn.innerHTML = `${icons.bookmark} Saved`;
    } else {
      btn.classList.remove('saved');
      btn.innerHTML = `${icons.bookmark} Save`;
    }
  });
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
  const descRaw = scheme.details || scheme.description || scheme.short_description || 'Verified government welfare scheme.';
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

  // Description snippet
  const isLongDesc = descRaw.length > 170;
  const shortDesc = isLongDesc ? descRaw.slice(0, 150).trim() + '…' : descRaw;
  const descHtml = isLongDesc ? `
    <p class="scheme-desc">
      <span class="desc-preview">${escapeHTML(shortDesc)}</span>
      <span class="desc-full" style="display:none;">${escapeHTML(descRaw)}</span>
      <button type="button" class="btn-read-more" onclick="toggleReadMore(this)">Read more</button>
    </p>
  ` : `
    <p class="scheme-desc">${escapeHTML(descRaw)}</p>
  `;

  // Expandable benefits snippet
  let benefitsSnippet = '';
  if (scheme.benefits && scheme.benefits.trim()) {
    const rawBen = scheme.benefits.trim();
    const isLongBen = rawBen.length > 160;
    const shortBen = isLongBen ? rawBen.slice(0, 140).trim() + '…' : rawBen;
    benefitsSnippet = `
      <div class="benefits">
        <div class="benefits-head">${icons.gift} GUARANTEED BENEFITS</div>
        <div class="benefits-content" style="font-size: 12px; color: #334155; line-height: 1.45;">
          ${isLongBen ? `
            <span class="desc-preview">${escapeHTML(shortBen)}</span>
            <span class="desc-full" style="display:none;">${escapeHTML(rawBen)}</span>
            <button type="button" class="btn-read-more" onclick="toggleReadMore(this)">Read more</button>
          ` : `<span>${escapeHTML(rawBen)}</span>`}
        </div>
      </div>
    `;
  }

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
      <h3 class="card-title-link" onclick="openSchemeDetailModal('${escapeHTML(schemeId)}')" style="cursor:pointer;" title="Click to view full scheme details &amp; application steps">${escapeHTML(title)}</h3>
      ${descHtml}
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
        <button type="button" class="footer-link btn-view-guidance" onclick="openSchemeDetailModal('${escapeHTML(schemeId)}')">${icons.clock} Step-by-Step Guide</button>
      </div>
    </article>`;
}

function toggleReadMore(btn) {
  const parent = btn.parentElement;
  if (!parent) return;
  const preview = parent.querySelector('.desc-preview');
  const full = parent.querySelector('.desc-full');
  if (!preview || !full) return;

  const isExpanded = full.style.display !== 'none';
  if (isExpanded) {
    full.style.display = 'none';
    preview.style.display = 'inline';
    btn.textContent = 'Read more';
  } else {
    full.style.display = 'inline';
    preview.style.display = 'none';
    btn.textContent = 'Read less';
  }
}

// ----------------------------------------------------------------------------
// Scheme Details & Application Guidance Modal
// ----------------------------------------------------------------------------
let currentModalScheme = null;

async function openSchemeDetailModal(schemeId) {
  const modal = document.getElementById('schemeDetailModal');
  if (!modal) return;
  const titleEl = document.getElementById('modalDetailTitle');
  const bodyEl = document.getElementById('modalDetailBody');
  const saveBtn = document.getElementById('modalSaveBtn');
  const applyBtn = document.getElementById('modalApplyBtn');
  const aiBtn = document.getElementById('modalAiBtn');

  modal.classList.add('open');
  bodyEl.innerHTML = `
    <div style="text-align: center; padding: 30px; color: #64748b;">
      <div style="display:inline-block; width:20px; height:20px; border:2px solid #047857; border-top-color:transparent; border-radius:50%; animation:spin 0.8s linear infinite; margin-bottom:8px;"></div>
      <div>Loading official scheme details &amp; application steps…</div>
    </div>
  `;

  try {
    let scheme = currentSchemes.find(s => (s.id || s.slug) === schemeId);
    if (!scheme) {
      scheme = await API.getScheme(schemeId);
    }
    currentModalScheme = scheme;

    const title = scheme.title || scheme.name || 'Government Welfare Scheme';
    const category = scheme.primaryCategory || (scheme.categories && scheme.categories[0]) || scheme.category || 'General Welfare';
    const state = scheme.state || scheme.level || 'All India';
    const details = scheme.details || scheme.description || 'Verified welfare scheme.';
    const benefits = scheme.benefits || 'Check official gazette for direct benefit transfers and subsidies.';
    const eligibility = scheme.eligibility || 'Eligible for resident citizens fulfilling age and income criteria.';
    const portalUrl = scheme.portalUrl || scheme.application_url || 'https://www.india.gov.in';
    const docs = parseDocumentsList(scheme);
    const steps = scheme.steps || [];

    titleEl.textContent = title;

    if (applyBtn) applyBtn.href = portalUrl;
    if (aiBtn) aiBtn.href = `assistant.html?q=${encodeURIComponent('Explain ' + title + ' eligibility and application steps')}`;

    if (saveBtn) {
      const saved = isSaved(schemeId);
      saveBtn.innerHTML = saved ? '✓ Saved to Tracker' : '🔖 Bookmark Scheme';
      saveBtn.onclick = () => {
        handleSaveToggle(schemeId, saveBtn);
      };
    }

    const docsHtml = docs.map((d, i) => `
      <li class="doc-item" onclick="this.classList.toggle('checked')" style="cursor:pointer;">
        <span class="doc-check"></span>
        <span>${escapeHTML(d)}</span>
      </li>
    `).join('');

    const stepsHtml = (steps.length > 0 ? steps : [
      { stepNumber: 1, title: 'Visit Official Portal', description: `Open ${portalUrl} and navigate to scheme registrations.` },
      { stepNumber: 2, title: 'Identity Verification', description: 'Authenticate using Aadhaar or Mobile OTP.' },
      { stepNumber: 3, title: 'Upload Documents', description: 'Attach identity, income, and bank passbook copies.' },
      { stepNumber: 4, title: 'Save Reference ID', description: 'Submit form and download the acknowledgment receipt.' }
    ]).map((s, idx) => `
      <div class="step-item" style="display:flex; gap:12px; margin-bottom:10px; background:#f8fafc; padding:10px 14px; border-radius:8px; border:1px solid #e2e8f0;">
        <div class="step-num" style="width:24px; height:24px; border-radius:50%; background:#064d3b; color:#fff; display:grid; place-items:center; font-size:11px; font-weight:800; flex-shrink:0;">${s.stepNumber || idx + 1}</div>
        <div class="step-info">
          <h4 style="font-size:13.5px; font-weight:700; color:#1e293b; margin-bottom:3px;">${escapeHTML(s.title || `Step ${idx + 1}`)}</h4>
          <p style="font-size:12.5px; color:#475569; line-height:1.45;">${escapeHTML(s.description || '')}</p>
        </div>
      </div>
    `).join('');

    bodyEl.innerHTML = `
      <div style="display:flex; gap:8px; align-items:center; margin-bottom:12px; flex-wrap:wrap;">
        <span class="cat-tag" style="background:#f1f5f9; color:#334155; font-size:11px; font-weight:700; padding:3px 8px; border-radius:4px;">${escapeHTML(category.toUpperCase())}</span>
        <span class="loc-tag" style="background:#eff6ff; color:#1d4ed8; font-size:11px; font-weight:700; padding:3px 8px; border-radius:4px;">${escapeHTML(state)}</span>
        <span class="status-badge status-active" style="background:#ecfdf5; color:#047857; font-size:11px; font-weight:700; padding:3px 8px; border-radius:4px;">Verified Gazette</span>
      </div>

      <div style="margin-bottom:16px;">
        <h4 style="font-size:13px; font-weight:800; color:#0f766e; text-transform:uppercase; margin-bottom:4px;">Scheme Overview</h4>
        <p style="font-size:13px; color:#334155; line-height:1.5;">${escapeHTML(details)}</p>
      </div>

      <div style="margin-bottom:16px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:12px 14px;">
        <h4 style="font-size:13px; font-weight:800; color:#15803d; text-transform:uppercase; margin-bottom:4px;">🎁 Guaranteed Benefits</h4>
        <p style="font-size:13px; color:#166534; line-height:1.5;">${escapeHTML(benefits)}</p>
      </div>

      <div style="margin-bottom:16px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px 14px;">
        <h4 style="font-size:13px; font-weight:800; color:#334155; text-transform:uppercase; margin-bottom:4px;">📋 Eligibility Criteria</h4>
        <p style="font-size:13px; color:#475569; line-height:1.5;">${escapeHTML(eligibility)}</p>
      </div>

      <div style="margin-bottom:16px;">
        <h4 style="font-size:13px; font-weight:800; color:#0f766e; text-transform:uppercase; margin-bottom:6px;">Document Checklist (Click to Tick)</h4>
        <ul class="doc-list">${docsHtml}</ul>
      </div>

      <div style="margin-bottom:16px;">
        <h4 style="font-size:13px; font-weight:800; color:#0f766e; text-transform:uppercase; margin-bottom:8px;">Step-by-Step Official Application Guidance</h4>
        <div class="steps-flow">${stepsHtml}</div>
      </div>
    `;
  } catch (err) {
    bodyEl.innerHTML = `<p style="color:#ef4444; padding:20px;">Could not load scheme details. Please retry.</p>`;
  }
}

// ----------------------------------------------------------------------------
// Scheme Save & Bookmark Synchronization
// ----------------------------------------------------------------------------
async function handleSaveToggle(schemeId, buttonElement = null) {
  const isCurrentlySaved = isSaved(schemeId);
  const schemeObj = currentSchemes.find(s => (s.id || s.slug) === schemeId) || { id: schemeId, title: schemeId };

  try {
    if (isCurrentlySaved) {
      savedSchemesSet.delete(String(schemeId));
      if (typeof toggleLocalSaved === 'function') toggleLocalSaved(schemeObj);
      if (typeof isLoggedIn === 'function' && isLoggedIn()) {
        await API.removeSavedScheme(schemeId).catch(() => { });
      }
      if (buttonElement) {
        buttonElement.classList.remove('saved');
        buttonElement.innerHTML = buttonElement.id === 'modalSaveBtn' ? '🔖 Bookmark Scheme' : `${icons.bookmark} Save`;
      }
      showToast('Scheme removed from your Scheme Tracker', 'info');
    } else {
      savedSchemesSet.add(String(schemeId));
      if (typeof toggleLocalSaved === 'function') toggleLocalSaved(schemeObj);
      if (typeof isLoggedIn === 'function' && isLoggedIn()) {
        await API.saveScheme(schemeId).catch(() => { });
      }
      if (buttonElement) {
        buttonElement.classList.add('saved');
        buttonElement.innerHTML = buttonElement.id === 'modalSaveBtn' ? '✓ Saved to Tracker' : `${icons.bookmark} Saved`;
      }
      showToast('Scheme saved to your Scheme Tracker!', 'success');
    }
    updateAllSaveButtons();
  } catch (err) {
    console.error('Failed to toggle bookmark:', err);
  }
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
    updateAllSaveButtons();
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
      catSelect.innerHTML = `<option value="All" selected>✓ All Categories Selected</option>` +
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
  const cleanCat = (categoryVal === 'All' || categoryVal.includes('All Categories')) ? '' : categoryVal;

  try {
    const res = await fetch('/api/schemes/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state: stateVal.includes('All India') ? 'All India' : stateVal,
        age: parseInt(ageVal, 10),
        gender: genderVal,
        category: cleanCat,
        occupation: cleanCat === 'Agriculture' ? 'farmer' : (cleanCat === 'Education' ? 'student' : undefined)
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
      updateAllSaveButtons();
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
  initSavedState();
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

  // Dynamic filter updates on select changes (Bug fix 1)
  const stateSelect = document.getElementById("state");
  const catSelect = document.getElementById("category");
  const searchInput = document.getElementById("search");

  const runSearch = () => {
    const q = searchInput ? searchInput.value.trim() : '';
    const state = stateSelect ? stateSelect.value : 'All';
    const cat = catSelect ? catSelect.value : 'All';
    fetchSchemes(q, state, cat, 1, false);
  };

  if (stateSelect) stateSelect.addEventListener("change", runSearch);
  if (catSelect) catSelect.addEventListener("change", runSearch);

  const resetBtn = document.getElementById("resetFilters");
  if (resetBtn) resetBtn.addEventListener("click", resetAllFilters);

  // Scheme card clicks delegation (Document ticking & Bookmark saving)
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
        e.preventDefault();
        const id = saveBtn.dataset.scheme;
        handleSaveToggle(id, saveBtn);
      }
    });
  }

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
      const state = stateSelect ? stateSelect.value : 'All';
      const cat = catSelect ? catSelect.value : 'All';
      fetchSchemes(q, state, cat, currentPage + 1, true);
    });
  }

  // Modal close handlers
  const closeDetailBtn = document.getElementById("closeDetailModal");
  if (closeDetailBtn) {
    closeDetailBtn.addEventListener("click", () => {
      const modal = document.getElementById("schemeDetailModal");
      if (modal) modal.classList.remove("open");
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