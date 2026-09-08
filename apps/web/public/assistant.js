let conversationHistory = [];
let activeProfile = {};
let isVoiceSupported = 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
let recognition = null;
let currentSpeakingBtn = null;
// Speech synthesis toggle helper (Fix for Task 3)
function toggleSpeech(text, btnElement) {
    if (!('speechSynthesis' in window)) {
        alert('Text-to-speech is not supported in this browser.');
        return;
    }
    // If already speaking, STOP immediately
    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
        window.speechSynthesis.cancel();
        resetAllListenButtons();
        return;
    }
    // Reset any other active buttons
    resetAllListenButtons();
    // Clean text for natural speech
    const cleanSpeechText = text
        .replace(/[✓⚠️•\-]/g, ' ')
        .replace(/\n+/g, '. ')
        .trim();
    const utterance = new SpeechSynthesisUtterance(cleanSpeechText);
    utterance.lang = 'en-IN';
    utterance.rate = 1.0;
    utterance.onstart = () => {
        currentSpeakingBtn = btnElement;
        btnElement.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
      Stop
    `;
        btnElement.classList.add('speaking');
        btnElement.style.background = '#fee2e2';
        btnElement.style.color = '#dc2626';
    };
    utterance.onend = () => {
        resetAllListenButtons();
    };
    utterance.onerror = () => {
        resetAllListenButtons();
    };
    window.speechSynthesis.speak(utterance);
}
function resetAllListenButtons() {
    document.querySelectorAll('.js-speak-btn').forEach(btn => {
        btn.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
      Listen
    `;
        btn.classList.remove('speaking');
        btn.style.background = '';
        btn.style.color = '';
    });
    currentSpeakingBtn = null;
}
function escapeHTML(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
// Update profile badge in UI
function updateProfileBadge() {
    const parts = [];
    if (activeProfile.state) parts.push(`📍 ${activeProfile.state}`);
    if (activeProfile.age) parts.push(`${activeProfile.age} yrs`);
    if (activeProfile.occupation) parts.push(`💼 ${activeProfile.occupation}`);
    if (activeProfile.gender) parts.push(activeProfile.gender);
    if (activeProfile.category) parts.push(`🏷️ ${activeProfile.category}`);
    if (activeProfile.income) parts.push(`₹ ${activeProfile.income}`);
    let bar = document.getElementById("profileStatusBar");
    if (parts.length > 0) {
        if (!bar) {
            bar = document.createElement("div");
            bar.id = "profileStatusBar";
            bar.className = "profile-status-bar";
            const chatPanel = document.querySelector(".chat-panel");
            const chatLog = document.getElementById("chatLog");
            chatPanel.insertBefore(bar, chatLog);
        }
        bar.innerHTML = `<span>Profile: ${parts.join(' • ')}</span>`;
    }
}
// Render message bubbles in ChatGPT style
function createBubble(role, content, extra = {}) {
    const el = document.createElement("div");
    el.className = `bubble bubble-${role}`;
    if (role === "user") {
        el.innerHTML = `<p>${escapeHTML(content)}</p>`;
    } else {
        // Quick reply pills
        let quickRepliesHtml = "";
        if (extra.quickReplies && extra.quickReplies.length > 0) {
            quickRepliesHtml = `
        <div class="quick-replies-wrap">
          ${extra.quickReplies.map(qr => `
            <button type="button" class="quick-reply-pill js-quick-reply" data-text="${escapeHTML(qr)}">
              ${escapeHTML(qr)}
            </button>
          `).join("")}
        </div>
      `;
        }
        let formattedText = content
            .split('\n\n')
            .map(p => {
                let line = escapeHTML(p).replace(/\n/g, '<br>');
                // Convert [Text](https://...) markdown links
                line = line.replace(/\[(.*?)\]\((https?:\/\/[^\s\)\<\>\"]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="portal-apply-link">$1 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M7 17L17 7"/><path d="M7 7h10v10"/></svg></a>');
                return `<p>${line}</p>`;
            })
            .join('');
        el.innerHTML = `
      <div class="bubble-ai-header">
        <span class="ai-avatar">AI</span>
        <span>Navi</span>
      </div>
      <div>${formattedText}</div>
      ${quickRepliesHtml}
      <div class="bubble-actions">
        <button type="button" class="bubble-action-btn js-copy-btn">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy
        </button>
        <button type="button" class="bubble-action-btn js-speak-btn">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
          Listen
        </button>
      </div>
    `;
        // Attach quick reply handlers
        el.querySelectorAll('.js-quick-reply').forEach(btn => {
            btn.addEventListener('click', () => {
                ask(btn.dataset.text);
            });
        });
        // Attach copy handler
        const copyBtn = el.querySelector('.js-copy-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(content).then(() => {
                    copyBtn.textContent = 'Copied!';
                    setTimeout(() => { copyBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy`; }, 1500);
                });
            });
        }
        // Attach speak / listen toggle handler (Task 3 bugfix)
        const speakBtn = el.querySelector('.js-speak-btn');
        if (speakBtn) {
            speakBtn.addEventListener('click', () => {
                toggleSpeech(content, speakBtn);
            });
        }
    }
    return el;
}
function showTypingIndicator() {
    const log = document.getElementById("chatLog");
    const el = document.createElement("div");
    el.className = "bubble bubble-ai typing-bubble";
    el.id = "typingIndicator";
    el.innerHTML = `
    <span class="ai-avatar">AI</span>
    <span class="typing-dot"></span>
    <span class="typing-dot"></span>
    <span class="typing-dot"></span>
    <span style="font-size: 11px; color: #64748b; margin-left: 6px;">Navi is checking official records...</span>
  `;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
}
function removeTypingIndicator() {
    const el = document.getElementById("typingIndicator");
    if (el) el.remove();
}
function renderSources(sources) {
    const list = document.getElementById("sourcesList");
    if (!sources || sources.length === 0) return;
    list.innerHTML = sources.map(s => `
    <article class="source-card">
      <div style="display: flex; justify-content: space-between; align-items: baseline;">
        <strong>${escapeHTML(s.title)}</strong>
      </div>
      <span>Level: ${escapeHTML(s.level)} • State: ${escapeHTML(s.state)}</span>
      <div class="source-badge ${s.isExpired ? 'expired' : 'open'}">
        ${escapeHTML(s.deadline)}
      </div>
    </article>
  `).join("");
}
async function ask(text) {
    if (!text || !text.trim()) return;
    const log = document.getElementById("chatLog");
    // If speaking when a new message is sent, stop speech
    if ('speechSynthesis' in window && window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        resetAllListenButtons();
    }
    // Append user message
    log.appendChild(createBubble("user", text));
    log.scrollTop = log.scrollHeight;
    showTypingIndicator();
    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                history: conversationHistory,
                userProfile: activeProfile
            })
        });

        const data = await res.json();
        removeTypingIndicator();
        if (data.userProfile) {
            activeProfile = { ...activeProfile, ...data.userProfile };
            updateProfileBadge();
        }
        // Append AI response with clean quick replies
        log.appendChild(createBubble("ai", data.reply, {
            quickReplies: data.quickReplies || []
        }));
        // Update conversation history
        conversationHistory.push({ role: 'user', text: text });
        conversationHistory.push({ role: 'model', text: data.reply });
        if (data.sources && data.sources.length > 0) {
            renderSources(data.sources);
        }
    } catch (err) {
        removeTypingIndicator();
        log.appendChild(createBubble("ai", "I experienced a temporary connection issue. Please try again."));
    }
    log.scrollTop = log.scrollHeight;
}
// Step-by-Step Portal Modal Logic
async function openStepsModal(slug) {
    const modal = document.getElementById('stepsModal');
    const title = document.getElementById('modalSchemeTitle');
    const body = document.getElementById('modalStepsBody');
    body.innerHTML = '<p>Loading official portal steps...</p>';
    modal.classList.add('open');
    try {
        const res = await fetch(`/api/schemes/${encodeURIComponent(slug)}`);
        const scheme = await res.json();
        title.textContent = scheme.title;

        const stepsHtml = (scheme.steps || []).map((step, idx) => `
      <div class="step-item">
        <div class="step-num">${step.stepNumber || idx + 1}</div>
        <div class="step-info">
          <h4>${escapeHTML(step.title)}</h4>
          <p>${escapeHTML(step.description)}</p>
        </div>
      </div>
    `).join("");
        const docsHtml = (scheme.documentsList || []).map(doc => `
      <li class="doc-item" onclick="this.classList.toggle('checked')">
        <span class="doc-check"></span>
        <span>${escapeHTML(doc)}</span>
      </li>
    `).join("");

        body.innerHTML = `
      <div style="background: #f8fafc; border-radius: 8px; padding: 12px; margin-bottom: 20px;">
        <div style="font-weight: 700; color: var(--teal-deep); font-size: 12px; margin-bottom: 4px;">REQUIRED DOCUMENTS CHECKLIST</div>
        <ul class="doc-list">${docsHtml || '<li>Standard Identity & Address Proof (Aadhaar / Ration Card)</li>'}</ul>
      </div>
      <div style="font-weight: 800; font-size: 14px; margin-bottom: 12px; color: var(--text);">HOW TO APPLY — OFFICIAL PORTAL PROCEDURE</div>
      <div class="steps-flow">${stepsHtml}</div>
      <div style="margin-top: 20px; padding: 12px; background: #ecfdf5; border-radius: 8px; font-size: 12px; color: #047857;">
        <strong>Official Submission Note:</strong> Once submitted, save your unique Application Reference ID and acknowledgment slip.
      </div>
    `;
    } catch (err) {
        body.innerHTML = '<p>Could not load steps for this scheme.</p>';
    }
}
// Setup Loan Calculator
function setupLoanCalculator() {
    const calcModal = document.getElementById('calcModal');
    const openBtn = document.getElementById('openCalcBtn');
    const closeBtn = document.getElementById('closeCalcModal');
    const runBtn = document.getElementById('runCalcBtn');
    const askAiBtn = document.getElementById('askAiAboutCalcBtn');
    if (openBtn) openBtn.addEventListener('click', () => calcModal.classList.add('open'));
    if (closeBtn) closeBtn.addEventListener('click', () => calcModal.classList.remove('open'));
    if (runBtn) {
        runBtn.addEventListener('click', async () => {
            const amount = document.getElementById('calcAmount').value;
            const schemeType = document.getElementById('calcScheme').value;
            const category = document.getElementById('calcCategory').value;
            const area = document.getElementById('calcArea').value;
            try {
                const res = await fetch('/api/calculate-loan', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ amount, schemeType, category, area })
                });
                const data = await res.json();
                document.getElementById('calcResults').style.display = 'block';
                document.getElementById('resSubsidy').textContent = `₹${(data.govtSubsidyAmount || 0).toLocaleString('en-IN')} (${data.govtSubsidyPercent}%)`;
                document.getElementById('resMargin').textContent = `₹${(data.ownContributionAmount || 0).toLocaleString('en-IN')} (${data.ownContributionPercent}%)`;
                document.getElementById('resLoan').textContent = `₹${(data.netBankLoanAmount || 0).toLocaleString('en-IN')}`;
                document.getElementById('resEMI').textContent = `₹${(data.monthlyEMI || 0).toLocaleString('en-IN')} / mo`;
                document.getElementById('resSummary').textContent = data.summary;
            } catch (err) {
                alert('Could not calculate loan.');
            }
        });
    }

    if (askAiBtn) {
        askAiBtn.addEventListener('click', () => {
            calcModal.classList.remove('open');
            const amount = document.getElementById('calcAmount').value;
            const schemeType = document.getElementById('calcScheme').value;
            const category = document.getElementById('calcCategory').value;
            ask(`Calculate the exact subsidy, margin money, and step-by-step application process for a ₹${amount} loan under ${schemeType} for ${category}.`);
        });
    }
}
function initAssistant() {
    const form = document.getElementById("chatForm");
    const input = document.getElementById("chatInput");
    const micBtn = document.getElementById("micBtn");
    const clearBtn = document.getElementById("clearChatBtn");
    const closeStepsModalBtn = document.getElementById("closeStepsModal");
    const modalDoneBtn = document.getElementById("modalDoneBtn");
    form.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.value = "";
        ask(text);
    });
    document.querySelectorAll(".prompt-chip").forEach((btn) => {
        btn.addEventListener("click", () => ask(btn.dataset.prompt));
    });
    if (clearBtn) {
        clearBtn.addEventListener("click", () => {
            if ('speechSynthesis' in window) window.speechSynthesis.cancel();
            conversationHistory = [];
            activeProfile = {};
            const bar = document.getElementById("profileStatusBar");
            if (bar) bar.remove();
            document.getElementById("chatLog").innerHTML = "";
            renderWelcomeGreeting();
        });
    }
    if (closeStepsModalBtn) {
        closeStepsModalBtn.addEventListener('click', () => {
            document.getElementById('stepsModal').classList.remove('open');
        });
    }
    if (modalDoneBtn) {
        modalDoneBtn.addEventListener('click', () => {
            document.getElementById('stepsModal').classList.remove('open');
        });
    }
    // Voice Input (SpeechRecognition)
    if (isVoiceSupported && micBtn) {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRec();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-IN';
        recognition.onstart = () => {
            micBtn.classList.add('recording');
        };
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            input.value = transcript;
            micBtn.classList.remove('recording');
            ask(transcript);
            input.value = "";
        };
        recognition.onerror = () => {
            micBtn.classList.remove('recording');
        };
        recognition.onend = () => {
            micBtn.classList.remove('recording');
        };
        micBtn.addEventListener('click', () => {
            try {
                recognition.start();
            } catch (e) {
                recognition.stop();
            }
        });
    } else if (micBtn) {
        micBtn.style.display = 'none';
    }
    setupLoanCalculator();
    function renderWelcomeGreeting() {
        document.getElementById("chatLog").appendChild(
            createBubble(
                "ai",
                "👋 Hi! I'm Navi.\nI can help you discover government welfare schemes you may be eligible for, calculate subsidies, or explain exact application steps.\n\nClick an option below or type your question in plain English:",
                {
                    quickReplies: ['Find schemes for me', 'Farmer Subsidies', 'Student Scholarships', 'Calculate Loan Subsidy']
                }
            )
        );
    }
    const preset = new URLSearchParams(location.search).get("q");
    if (preset) {
        ask(preset);
    } else {
        renderWelcomeGreeting();
    }
}
document.addEventListener("DOMContentLoaded", initAssistant);