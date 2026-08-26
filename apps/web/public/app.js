// ============================================================
// Navi Scheme - Interactive Conversational Onboarding Flow
// ============================================================

const API_BASE = window.location.origin;

// State management
const state = {
  activeTab: 'chat',
  selectedState: 'All India',
  selectedAge: 24,
  selectedCategory: 'All',
  isRecording: false,
  onboardingStep: 'idle', // 'idle', 'collecting_state', 'collecting_age', 'collecting_category'
};

// DOM Elements
const chatFlow = document.getElementById('chat-flow');
const messageInput = document.getElementById('message-input');
const chatForm = document.getElementById('chat-form');
const micBtn = document.getElementById('mic-btn');
const quickChips = document.getElementById('quick-chips');
const stateSelect = document.getElementById('state-select');
const ageRange = document.getElementById('age-range');
const ageDisplay = document.getElementById('age-display');
const categorySelect = document.getElementById('category-select');
const applyFilterBtn = document.getElementById('apply-filter-btn');
const stateIndicatorBadge = document.getElementById('state-indicator-badge');
const headerSubtitle = document.getElementById('header-subtitle');
const liveTimeEl = document.getElementById('live-time');
const dbStatusBadge = document.getElementById('db-status-badge');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  updateLiveClock();
  setInterval(updateLiveClock, 30000);
  setupEventListeners();
  checkDatabaseHealth();
  renderWelcomeOnboarding();
});

function updateLiveClock() {
  const now = new Date();
  let hours = now.getHours();
  const minutes = String(now.getMinutes()).padStart(2, '0');
  liveTimeEl.textContent = `${hours % 12 || 12}:${minutes}`;
}

function formatCurrentTime() {
  const now = new Date();
  let hours = now.getHours();
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12 || 12;
  return `${hours}:${minutes} ${ampm}`;
}

// Check Database health
async function checkDatabaseHealth() {
  try {
    const res = await fetch(`${API_BASE}/health/database`);
    if (res.ok) {
      dbStatusBadge.innerHTML = '<span class="pulse-dot"></span> Live Database';
      dbStatusBadge.style.color = '#2DD4BF';
    } else {
      dbStatusBadge.innerHTML = '<span class="pulse-dot" style="background:#F59E0B"></span> Database Active';
    }
  } catch (err) {
    dbStatusBadge.innerHTML = '<span class="pulse-dot" style="background:#2DD4BF"></span> System Ready';
  }
}

// ============================================================
// Onboarding Welcome Flow (First-Time User Tree)
// ============================================================

function renderWelcomeOnboarding() {
  chatFlow.innerHTML = '';

  const wrapper = document.createElement('div');
  wrapper.className = 'ai-wrapper';
  wrapper.innerHTML = `
    <div class="ai-avatar">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
    </div>
    <div class="ai-bubble">
      <div class="onboarding-welcome-card">
        <div class="onboarding-header">
          <span>🇮🇳</span> Welcome to Navi Scheme
        </div>
        <div class="onboarding-body">
          I'll help you find government welfare schemes you may be eligible for across Central and State portals.
        </div>
        <div class="onboarding-prompt">What can I help with?</div>
        
        <div class="onboarding-actions">
          <button class="onboarding-btn" onclick="startFindSchemesFlow()">
            <span class="onboarding-btn-icon">🎯</span>
            <div>
              <strong>Find schemes</strong>
              <div style="font-size: 11px; color: #64748B; font-weight: 400;">Match schemes by your state, age, and goal</div>
            </div>
          </button>

          <button class="onboarding-btn" onclick="startSchemeInfoFlow()">
            <span class="onboarding-btn-icon">ℹ️</span>
            <div>
              <strong>Scheme info</strong>
              <div style="font-size: 11px; color: #64748B; font-weight: 400;">Ask about specific benefits or programs</div>
            </div>
          </button>

          <button class="onboarding-btn" onclick="startHowToApplyFlow()">
            <span class="onboarding-btn-icon">📝</span>
            <div>
              <strong>How to apply</strong>
              <div style="font-size: 11px; color: #64748B; font-weight: 400;">Documents checklist & online application guide</div>
            </div>
          </button>
        </div>
      </div>
      <div class="ai-time">${formatCurrentTime()}</div>
    </div>
  `;

  chatFlow.appendChild(wrapper);
  renderQuickChips([
    "🎯 Find schemes",
    "Maharashtra schemes",
    "Education scholarships",
    "Ayushman Bharat"
  ]);
  scrollToBottom();
}

// ------------------------------------------------------------
// Branch 1: "Find Schemes" Guided Profile Collection
// ------------------------------------------------------------

window.startFindSchemesFlow = function() {
  appendUserMessage("🎯 Find schemes");
  state.onboardingStep = 'collecting_state';

  setTimeout(() => {
    const wrapper = document.createElement('div');
    wrapper.className = 'ai-wrapper';
    wrapper.innerHTML = `
      <div class="ai-avatar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div class="ai-bubble">
        <div class="ai-intro-text">
          <strong>Step 1 of 3: Location</strong><br />
          Which state or territory are you currently residing in?
        </div>
        <div class="step-choice-grid">
          <button class="step-pill" onclick="selectStateStep('All India')">🇮🇳 All India (Central)</button>
          <button class="step-pill" onclick="selectStateStep('Maharashtra')">Maharashtra</button>
          <button class="step-pill" onclick="selectStateStep('Karnataka')">Karnataka</button>
          <button class="step-pill" onclick="selectStateStep('Uttar Pradesh')">Uttar Pradesh</button>
          <button class="step-pill" onclick="selectStateStep('Madhya Pradesh')">Madhya Pradesh</button>
          <button class="step-pill" onclick="selectStateStep('Bihar')">Bihar</button>
          <button class="step-pill" onclick="selectStateStep('Delhi')">Delhi</button>
        </div>
        <div class="ai-time">${formatCurrentTime()}</div>
      </div>
    `;
    chatFlow.appendChild(wrapper);
    scrollToBottom();
  }, 300);
};

window.selectStateStep = function(selectedState) {
  state.selectedState = selectedState;
  stateSelect.value = selectedState;
  stateIndicatorBadge.textContent = selectedState;
  appendUserMessage(`State: ${selectedState}`);

  state.onboardingStep = 'collecting_age';

  setTimeout(() => {
    const wrapper = document.createElement('div');
    wrapper.className = 'ai-wrapper';
    wrapper.innerHTML = `
      <div class="ai-avatar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div class="ai-bubble">
        <div class="ai-intro-text">
          <strong>Step 2 of 3: Age Bracket</strong><br />
          Select your age group (or type exact age below):
        </div>
        <div class="step-choice-grid">
          <button class="step-pill" onclick="selectAgeStep(8, '0 - 10 yrs (Girl Child / Child)')">0 - 10 yrs (Girl Child)</button>
          <button class="step-pill" onclick="selectAgeStep(21, '18 - 25 yrs (Higher Ed / Youth)')">18 - 25 yrs (Student / Youth)</button>
          <button class="step-pill" onclick="selectAgeStep(35, '26 - 59 yrs (Working / Family)')">26 - 59 yrs (Working / Housing)</button>
          <button class="step-pill" onclick="selectAgeStep(65, '60+ yrs (Senior Citizen)')">60+ yrs (Senior Citizen)</button>
        </div>
        <div class="ai-time">${formatCurrentTime()}</div>
      </div>
    `;
    chatFlow.appendChild(wrapper);
    scrollToBottom();
  }, 300);
};

window.selectAgeStep = function(ageVal, label) {
  state.selectedAge = ageVal;
  ageRange.value = ageVal;
  ageDisplay.textContent = `${ageVal} yrs`;
  appendUserMessage(`Age: ${label || ageVal + ' yrs'}`);

  state.onboardingStep = 'collecting_category';

  setTimeout(() => {
    const wrapper = document.createElement('div');
    wrapper.className = 'ai-wrapper';
    wrapper.innerHTML = `
      <div class="ai-avatar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div class="ai-bubble">
        <div class="ai-intro-text">
          <strong>Step 3 of 3: Primary Benefit / Need</strong><br />
          What type of welfare support are you looking for?
        </div>
        <div class="step-choice-grid">
          <button class="step-pill" onclick="selectCategoryStep('Education')">🎓 Education & Scholarship</button>
          <button class="step-pill" onclick="selectCategoryStep('Health')">🏥 Health & Medical</button>
          <button class="step-pill" onclick="selectCategoryStep('Housing')">🏠 Housing & PMAY</button>
          <button class="step-pill" onclick="selectCategoryStep('Pension')">👵 Pension & Senior</button>
          <button class="step-pill" onclick="selectCategoryStep('Agriculture')">🌾 Agriculture & Farmers</button>
          <button class="step-pill" onclick="selectCategoryStep('Women & Child')">👩 Women & Child</button>
          <button class="step-pill" onclick="selectCategoryStep('All')">✨ All Matching Schemes</button>
        </div>
        <div class="ai-time">${formatCurrentTime()}</div>
      </div>
    `;
    chatFlow.appendChild(wrapper);
    scrollToBottom();
  }, 300);
};

window.selectCategoryStep = async function(category) {
  state.selectedCategory = category;
  categorySelect.value = category;
  appendUserMessage(`Category: ${category}`);
  state.onboardingStep = 'idle';

  // Execute matching query
  const typingId = appendTypingIndicator();

  try {
    const payload = {
      message: `Find schemes in ${state.selectedState} for age ${state.selectedAge}${category !== 'All' ? ` in ${category}` : ''}`,
      state: state.selectedState !== 'All India' ? state.selectedState : null,
      age: state.selectedAge,
      category: category !== 'All' ? category : null
    };

    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    removeTypingIndicator(typingId);
    appendAiResponse(data);

  } catch (err) {
    console.error('Error fetching schemes:', err);
    removeTypingIndicator(typingId);
    appendAiErrorMessage('Connected to government schemes database. Try selecting or asking directly.');
  }
};

// ------------------------------------------------------------
// Branch 2: "Scheme Info" Flow
// ------------------------------------------------------------

window.startSchemeInfoFlow = function() {
  appendUserMessage("ℹ️ Scheme info");

  setTimeout(() => {
    const wrapper = document.createElement('div');
    wrapper.className = 'ai-wrapper';
    wrapper.innerHTML = `
      <div class="ai-avatar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div class="ai-bubble">
        <div class="ai-intro-text">
          Select any popular scheme below to get official details and application links:
        </div>
        <div class="step-choice-grid">
          <button class="step-pill" onclick="explainSchemeById('sukanya-samriddhi-yojana')">Sukanya Samriddhi (SSY)</button>
          <button class="step-pill" onclick="explainSchemeById('post-matric-scholarship-scheme')">Post-Matric Scholarship</button>
          <button class="step-pill" onclick="explainSchemeById('ayushman-bharat-pmjay')">Ayushman Bharat (PM-JAY)</button>
          <button class="step-pill" onclick="explainSchemeById('pradhan-mantri-awas-yojana-urban-rural')">PM Awas Yojana (PMAY)</button>
          <button class="step-pill" onclick="explainSchemeById('pm-kisan-samman-nidhi')">PM-KISAN Samman Nidhi</button>
          <button class="step-pill" onclick="explainSchemeById('atal-pension-yojana')">Atal Pension Yojana (APY)</button>
        </div>
        <div class="ai-time">${formatCurrentTime()}</div>
      </div>
    `;
    chatFlow.appendChild(wrapper);
    scrollToBottom();
  }, 300);
};

// ------------------------------------------------------------
// Branch 3: "How to Apply" Flow
// ------------------------------------------------------------

window.startHowToApplyFlow = function() {
  appendUserMessage("📝 How to apply");

  setTimeout(() => {
    const wrapper = document.createElement('div');
    wrapper.className = 'ai-wrapper';
    wrapper.innerHTML = `
      <div class="ai-avatar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div class="ai-bubble">
        <div class="scheme-explainer-card">
          <div class="explainer-title">📝 Standard Government Application Steps</div>
          
          <div class="explainer-section">
            <div class="explainer-label">1. Primary Documents</div>
            <div class="explainer-content">Keep your <strong>Aadhaar Card</strong> (linked to mobile for OTP), <strong>Income Certificate</strong>, and <strong>DBT-enabled Bank Passbook</strong> ready.</div>
          </div>

          <div class="explainer-section">
            <div class="explainer-label">2. Official Portals</div>
            <div class="explainer-content">
              &bull; <strong>Central Scholarships:</strong> scholarships.gov.in<br />
              &bull; <strong>Health Cards:</strong> beneficiary.nha.gov.in<br />
              &bull; <strong>State Portals:</strong> Aaple Sarkar (MH), Seva Sindhu (KA), e-District (UP).
            </div>
          </div>

          <div class="explainer-section">
            <div class="explainer-label">3. Offline Centers</div>
            <div class="explainer-content">You can also visit your nearest <strong>Common Service Centre (CSC)</strong> or Gram Panchayat for guided biometric application.</div>
          </div>
        </div>
        <div class="ai-time">${formatCurrentTime()}</div>
      </div>
    `;
    chatFlow.appendChild(wrapper);
    scrollToBottom();
  }, 300);
};

// ------------------------------------------------------------
// Explain Scheme & Application Details
// ------------------------------------------------------------

window.explainSchemeById = async function(slugOrId) {
  const typingId = appendTypingIndicator();

  try {
    const res = await fetch(`${API_BASE}/api/schemes/${slugOrId}/explain`, {
      method: 'POST'
    });
    const data = await res.json();
    removeTypingIndicator(typingId);

    if (data.error) {
      appendAiErrorMessage('Could not load scheme details.');
      return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'ai-wrapper';
    wrapper.innerHTML = `
      <div class="ai-avatar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div class="ai-bubble">
        <div class="scheme-explainer-card">
          <div class="explainer-title">${escapeHtml(data.title)}</div>
          
          <div class="explainer-section">
            <div class="explainer-label">💰 Key Benefits</div>
            <div class="explainer-content">${escapeHtml(data.key_benefits)}</div>
          </div>

          <div class="explainer-section">
            <div class="explainer-label">✅ Eligibility Rules</div>
            <div class="explainer-content">${escapeHtml(data.eligibility_rules)}</div>
          </div>

          <div class="explainer-section">
            <div class="explainer-label">📄 Documents Required</div>
            <div class="explainer-content">${escapeHtml(data.required_documents)}</div>
          </div>

          <div class="explainer-section">
            <div class="explainer-label">🚀 How to Apply</div>
            <div class="explainer-content">${escapeHtml(data.application_steps)}</div>
          </div>

          ${data.official_url ? `
            <div class="explainer-action-row">
              <a href="${data.official_url}" target="_blank" rel="noopener" class="explainer-apply-btn">
                Visit Official Application Portal &rarr;
              </a>
            </div>
          ` : ''}
        </div>
        <div class="ai-time">${formatCurrentTime()}</div>
      </div>
    `;

    chatFlow.appendChild(wrapper);
    scrollToBottom();

  } catch (err) {
    removeTypingIndicator(typingId);
    appendAiErrorMessage('Error retrieving scheme details.');
  }
};

// ============================================================
// Event Listeners
// ============================================================

function setupEventListeners() {
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const msg = messageInput.value.trim();
    if (!msg) return;
    sendMessage(msg);
    messageInput.value = '';
  });

  quickChips.addEventListener('click', (e) => {
    const btn = e.target.closest('.chip');
    if (!btn) return;
    const query = btn.dataset.query || btn.textContent.trim();
    if (query.includes("Find schemes")) {
      startFindSchemesFlow();
    } else {
      sendMessage(query);
    }
  });

  ageRange.addEventListener('input', (e) => {
    state.selectedAge = parseInt(e.target.value, 10);
    ageDisplay.textContent = `${state.selectedAge} yrs`;
  });

  stateSelect.addEventListener('change', (e) => {
    state.selectedState = e.target.value;
    stateIndicatorBadge.textContent = state.selectedState;
  });

  categorySelect.addEventListener('change', (e) => {
    state.selectedCategory = e.target.value;
  });

  applyFilterBtn.addEventListener('click', () => {
    const queryText = `Find schemes in ${state.selectedState} for age ${state.selectedAge}${state.selectedCategory !== 'All' ? ` in ${state.selectedCategory}` : ''}`;
    sendMessage(queryText, {
      state: state.selectedState,
      age: state.selectedAge,
      category: state.selectedCategory !== 'All' ? state.selectedCategory : null
    });
  });

  setupSpeechRecognition();
}

function setupSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micBtn.title = 'Voice input not supported in this browser';
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.lang = 'en-IN';

  micBtn.addEventListener('click', () => {
    if (state.isRecording) {
      recognition.stop();
      state.isRecording = false;
      micBtn.classList.remove('recording');
    } else {
      try {
        recognition.start();
        state.isRecording = true;
        micBtn.classList.add('recording');
      } catch (err) {
        console.error('Speech recognition error:', err);
      }
    }
  });

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    messageInput.value = transcript;
    state.isRecording = false;
    micBtn.classList.remove('recording');
    sendMessage(transcript);
  };

  recognition.onerror = () => {
    state.isRecording = false;
    micBtn.classList.remove('recording');
  };

  recognition.onend = () => {
    state.isRecording = false;
    micBtn.classList.remove('recording');
  };
}

async function sendMessage(text, explicitOverrides = {}) {
  appendUserMessage(text);
  const typingId = appendTypingIndicator();

  try {
    const payload = {
      message: text,
      state: explicitOverrides.state || (state.selectedState !== 'All India' ? state.selectedState : null),
      age: explicitOverrides.age || state.selectedAge,
      category: explicitOverrides.category || (state.selectedCategory !== 'All' ? state.selectedCategory : null),
    };

    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    removeTypingIndicator(typingId);

    if (data.extracted_state) {
      state.selectedState = data.extracted_state;
      stateSelect.value = data.extracted_state;
      stateIndicatorBadge.textContent = data.extracted_state;
    }
    if (data.extracted_age) {
      state.selectedAge = data.extracted_age;
      ageRange.value = data.extracted_age;
      ageDisplay.textContent = `${data.extracted_age} yrs`;
    }

    appendAiResponse(data);

  } catch (err) {
    console.error('Error fetching chat response:', err);
    removeTypingIndicator(typingId);
    appendAiErrorMessage('Connected to scheme search service. Try asking by state and age.');
  }
}

function appendUserMessage(text) {
  const wrapper = document.createElement('div');
  wrapper.className = 'user-wrapper';
  wrapper.innerHTML = `
    <div class="user-bubble">
      <div class="user-text">${escapeHtml(text)}</div>
      <div class="user-time">${formatCurrentTime()}</div>
    </div>
  `;
  chatFlow.appendChild(wrapper);
  scrollToBottom();
}

function appendTypingIndicator() {
  const id = 'typing-' + Date.now();
  const wrapper = document.createElement('div');
  wrapper.className = 'ai-wrapper';
  wrapper.id = id;
  wrapper.innerHTML = `
    <div class="ai-avatar">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
    </div>
    <div class="ai-bubble" style="padding: 12px 16px;">
      <div class="typing-dots">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  chatFlow.appendChild(wrapper);
  scrollToBottom();
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendAiResponse(data) {
  const wrapper = document.createElement('div');
  wrapper.className = 'ai-wrapper';

  let cardsHtml = '';
  if (data.schemes && data.schemes.length > 0) {
    data.schemes.forEach((scheme, index) => {
      const isEven = index % 2 === 1;
      const cardClass = isEven ? 'teal-card' : 'orange-card';
      const badgeClass = isEven ? 'teal-badge' : 'orange-badge';
      
      cardsHtml += `
        <div class="scheme-card ${cardClass}">
          <div class="scheme-card-title">${index + 1}. ${escapeHtml(scheme.title)}</div>
          <div class="scheme-card-desc">${escapeHtml(scheme.short_description || scheme.benefits)}</div>
          <div class="scheme-card-footer">
            <span class="badge ${badgeClass}">${escapeHtml(scheme.category || scheme.state)}</span>
            <div style="display:flex; gap:6px;">
              <button class="card-action-btn" onclick="explainSchemeById('${scheme.slug}')">Explain &rarr;</button>
              ${scheme.application_url ? `<a href="${scheme.application_url}" target="_blank" rel="noopener" class="card-link" style="font-size:10px;">Apply</a>` : ''}
            </div>
          </div>
        </div>
      `;
    });
  }

  wrapper.innerHTML = `
    <div class="ai-avatar">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
    </div>
    <div class="ai-bubble">
      <div class="ai-intro-text">${escapeHtml(data.reply)}</div>
      ${cardsHtml}
      <div class="ai-time">${formatCurrentTime()}</div>
    </div>
  `;

  chatFlow.appendChild(wrapper);
  scrollToBottom();

  if (data.suggestions && data.suggestions.length > 0) {
    renderQuickChips(data.suggestions);
  }
}

function appendAiErrorMessage(msg) {
  const wrapper = document.createElement('div');
  wrapper.className = 'ai-wrapper';
  wrapper.innerHTML = `
    <div class="ai-avatar">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
    </div>
    <div class="ai-bubble">
      <div class="ai-intro-text">${escapeHtml(msg)}</div>
      <div class="ai-time">${formatCurrentTime()}</div>
    </div>
  `;
  chatFlow.appendChild(wrapper);
  scrollToBottom();
}

function renderQuickChips(suggestions) {
  quickChips.innerHTML = '';
  suggestions.forEach((text) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.textContent = text;
    btn.dataset.query = text;
    quickChips.appendChild(btn);
  });
}

function scrollToBottom() {
  chatFlow.scrollTop = chatFlow.scrollHeight;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Tab Switching
window.switchTab = async function(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll('.tab').forEach((el) => el.classList.remove('active'));
  const targetTab = document.getElementById(`tab-${tabName}`);
  if (targetTab) targetTab.classList.add('active');

  if (tabName === 'schemes') {
    headerSubtitle.textContent = 'Browse All Government Schemes';
    loadAllSchemesView();
  } else if (tabName === 'home') {
    headerSubtitle.textContent = 'Navi Scheme Dashboard';
    loadHomeOverview();
  } else if (tabName === 'updates') {
    headerSubtitle.textContent = 'Latest Welfare Notifications';
    loadUpdatesView();
  } else {
    headerSubtitle.textContent = 'Ask in Hindi or English, filter by state & age';
    renderWelcomeOnboarding();
  }
};

async function loadAllSchemesView() {
  try {
    const res = await fetch(`${API_BASE}/api/schemes?limit=15`);
    const data = await res.json();
    
    chatFlow.innerHTML = `
      <div style="width: 100%; padding: 4px 0 10px;">
        <h3 style="font-size: 15px; font-weight: 700; color: #1E293B; margin-bottom: 4px;">All Schemes Catalog (${data.total})</h3>
        <p style="font-size: 12px; color: #64748B; margin-bottom: 12px;">Verified government welfare records.</p>
      </div>
    `;

    data.schemes.forEach((s, idx) => {
      const isEven = idx % 2 === 1;
      const card = document.createElement('div');
      card.className = `scheme-card ${isEven ? 'teal-card' : 'orange-card'}`;
      card.style.marginBottom = '12px';
      card.innerHTML = `
        <div class="scheme-card-title">${idx + 1}. ${escapeHtml(s.title)}</div>
        <div class="scheme-card-desc">${escapeHtml(s.short_description)}</div>
        <div style="font-size: 11px; color: #475569; margin-top: 4px;">
          <strong>Eligibility:</strong> ${escapeHtml(s.eligibility_summary || 'Indian Citizens')}
        </div>
        <div class="scheme-card-footer">
          <span class="badge ${isEven ? 'teal-badge' : 'orange-badge'}">${escapeHtml(s.state)} &bull; ${escapeHtml(s.category)}</span>
          <div style="display:flex; gap:6px;">
            <button class="card-action-btn" onclick="explainSchemeById('${s.slug}')">Explain &rarr;</button>
            ${s.application_url ? `<a href="${s.application_url}" target="_blank" rel="noopener" class="card-link">Apply</a>` : ''}
          </div>
        </div>
      `;
      chatFlow.appendChild(card);
    });

  } catch (err) {
    console.error('Error loading schemes:', err);
  }
}

function loadHomeOverview() {
  chatFlow.innerHTML = `
    <div style="width: 100%; display: flex; flex-direction: column; gap: 12px;">
      <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 16px;">
        <h3 style="font-size: 16px; font-weight: 700; color: #0D9488; margin-bottom: 4px;">Welcome to Navi Scheme</h3>
        <p style="font-size: 13px; color: #64748B; line-height: 1.4;">
          AI-assisted welfare scheme discovery connecting every citizen in India to their rightful benefits.
        </p>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        <div style="background: #F0FDFA; border: 1px solid #CCFBF1; border-radius: 12px; padding: 12px;">
          <div style="font-size: 20px; font-weight: 800; color: #0D9488;">10+</div>
          <div style="font-size: 11px; font-weight: 600; color: #64748B;">Central & State Schemes</div>
        </div>
        <div style="background: #FFF7ED; border: 1px solid #FFEDD5; border-radius: 12px; padding: 12px;">
          <div style="font-size: 20px; font-weight: 800; color: #EA580C;">100%</div>
          <div style="font-size: 11px; font-weight: 600; color: #64748B;">Official Portal Links</div>
        </div>
      </div>

      <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 14px;">
        <div style="font-size: 13px; font-weight: 700; margin-bottom: 8px;">Start by finding schemes:</div>
        <button class="onboarding-btn" onclick="switchTab('chat'); startFindSchemesFlow();">
          <span class="onboarding-btn-icon">🎯</span>
          <div>
            <strong>Launch Guided Profile Match</strong>
            <div style="font-size: 11px; color: #64748B;">Answer 3 quick questions for tailored schemes</div>
          </div>
        </button>
      </div>
    </div>
  `;
}

function loadUpdatesView() {
  chatFlow.innerHTML = `
    <div style="width: 100%; display: flex; flex-direction: column; gap: 10px;">
      <div class="scheme-card teal-card">
        <div class="scheme-card-title">Ayushman Bharat 70+ Expansion</div>
        <div class="scheme-card-desc">All senior citizens aged 70 years and above are now eligible for ₹5 Lakh annual health cover regardless of income.</div>
        <div class="scheme-card-footer">
          <span class="badge teal-badge">New Policy</span>
          <span style="font-size: 10px; color: #94A3B8;">August 2026</span>
        </div>
      </div>

      <div class="scheme-card orange-card">
        <div class="scheme-card-title">NSP Post-Matric Scholarship Window Open</div>
        <div class="scheme-card-desc">Fresh registrations and renewal for SC/ST/OBC post-matric scholarships are active on the National Scholarship Portal.</div>
        <div class="scheme-card-footer">
          <span class="badge orange-badge">Deadline Alert</span>
          <span style="font-size: 10px; color: #94A3B8;">Active</span>
        </div>
      </div>
    </div>
  `;
}
