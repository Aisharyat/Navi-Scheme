// ============================================================================
// NAVI SCHEME — Grounded AI Assistant (Connected to Backend & SQLite Facts)
// ============================================================================

let currentSessionId = getGuestSessionId();
let isResetting = false;

const WELCOME_INTRO_HTML = `
  <div class="assistant-intro-card" style="padding:16px 18px;background:#ffffff;border:1px solid #d1fae5;border-radius:14px;box-shadow:0 2px 8px rgba(0,0,0,0.03);margin-bottom:12px;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
      <div style="width:38px;height:38px;border-radius:50%;background:#047857;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px;">🏛️</div>
      <div>
        <h3 style="margin:0;font-size:15.5px;color:#065f46;font-weight:700;">NAVI SCHEME AI Guide</h3>
        <span style="font-size:12px;color:#6b7280;">Grounded in 3,400+ Official Central & State Gazettes</span>
      </div>
    </div>
    <p style="margin:0 0 10px;font-size:13.5px;color:#374151;line-height:1.55;">
      Namaste! I am your official assistant for discovering and applying for Indian Central and State Government welfare schemes, scholarships, farmer subsidies, and loan calculators.
    </p>
    <div style="display:flex;flex-wrap:wrap;gap:6px;font-size:11.5px;">
      <span style="background:#ecfdf5;color:#047857;padding:3px 9px;border-radius:999px;font-weight:600;">✓ 100% Free Application</span>
      <span style="background:#ecfdf5;color:#047857;padding:3px 9px;border-radius:999px;font-weight:600;">✓ Official Direct Portals</span>
      <span style="background:#ecfdf5;color:#047857;padding:3px 9px;border-radius:999px;font-weight:600;">✓ Zero Middlemen</span>
    </div>
  </div>
`;

// Helper to convert markdown syntax to clean HTML
function renderMarkdown(md) {
  if (!md) return "";
  
  // Normalize line endings
  let text = String(md).replace(/\r\n/g, "\n");

  let html = text
    .replace(/^#### (.*$)/gim, '<h4 style="margin:12px 0 6px;font-size:14px;color:#0f766e;font-weight:700;">$1</h4>')
    .replace(/^### (.*$)/gim, '<h3 style="margin:16px 0 8px;font-size:15.5px;color:#1e293b;font-weight:700;">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 style="margin:18px 0 10px;font-size:16.5px;color:#1e293b;font-weight:700;">$1</h2>')
    .replace(/\[(.*?)\]\((https?:\/\/[^\s\)]+)\)/gim, '<a href="$2" target="_blank" rel="noopener" style="color:#0284c7;text-decoration:underline;font-weight:600;">$1 ↗</a>')
    .replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/gim, "<em>$1</em>")
    .replace(/`([^`]+)`/gim, '<code style="background:#f1f5f9;padding:2px 5px;border-radius:4px;font-size:12px;">$1</code>')
    .replace(/^\s*([0-9]+)\.\s+(.*$)/gim, '<li style="margin-left:22px;margin-bottom:6px;list-style-type:decimal;">$2</li>')
    .replace(/^\s*[-•*]\s+(.*$)/gim, '<li style="margin-left:22px;margin-bottom:6px;list-style-type:disc;">$1</li>');

  // Replace double/single newlines with clean breaks outside of list items
  html = html
    .replace(/\n\n+/g, "<br><br>")
    .replace(/\n/g, "<br>")
    .replace(/(<\/li>)<br>/g, "$1")
    .replace(/<br>(<li)/g, "$1");

  return html;
}

function createBubble(role, contentHtml) {
  const el = document.createElement("div");
  el.className = `bubble bubble-${role}`;
  el.innerHTML = contentHtml;
  return el;
}

function renderSources(schemes = []) {
  const panel = document.getElementById("sourcesPanel");
  if (!panel) return;

  if (!schemes || schemes.length === 0) {
    panel.innerHTML = `
      <h2>Cited sources</h2>
      <p class="muted">Sources cited from the official gazette database appear here.</p>
    `;
    return;
  }

  const cardsHtml = schemes
    .map((s) => {
      const title = s.title || s.name || "Government Scheme";
      const body = s.issuing_body || s.ministry || s.state || "Government of India";
      const url = s.application_url || "https://www.india.gov.in";
      return `
        <article class="source-card" style="margin-bottom:10px;padding:12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;">
          <strong style="display:block;font-size:13px;color:#1e293b;margin-bottom:4px;">${title}</strong>
          <span style="display:block;font-size:11.5px;color:#64748b;margin-bottom:6px;">${body}</span>
          <a href="${url}" target="_blank" rel="noopener" style="font-size:11.5px;color:#0284c7;text-decoration:none;font-weight:600;">
            Official Portal ↗
          </a>
        </article>
      `;
    })
    .join("");

  panel.innerHTML = `
    <h2>Cited sources (${schemes.length})</h2>
    ${cardsHtml}
  `;
}

function renderSuggestions(suggestions = []) {
  const promptsPanel = document.querySelector(".prompts-panel");
  if (!promptsPanel || !suggestions || suggestions.length === 0) return;

  let chipsHtml = suggestions
    .map((text) => `<button type="button" class="prompt-chip" data-prompt="${text.replace(/"/g, "&quot;")}">${text}</button>`)
    .join("");

  const header = `<h2>Related follow-ups</h2>`;
  const note = `<div class="panel-note">Answers cite gazette rules. Always apply only on the official portal linked in the reply.</div>`;
  promptsPanel.innerHTML = `${header}${chipsHtml}${note}`;

  // Rebind click listeners
  promptsPanel.querySelectorAll(".prompt-chip").forEach((btn) => {
    btn.addEventListener("click", () => askQuestion(btn.getAttribute("data-prompt")));
  });
}

async function askQuestion(text) {
  if (!text || !text.trim()) return;

  const chatLog = document.getElementById("chatLog");
  const input = document.getElementById("chatInput");
  if (input) input.value = "";

  // Append user bubble
  chatLog.appendChild(createBubble("user", `<p>${text}</p>`));

  // Append typing indicator bubble
  const typingBubble = createBubble(
    "ai",
    `<p style="display:flex;align-items:center;gap:8px;color:#64748b;">
      <span class="spinner" style="display:inline-block;width:12px;height:12px;border:2px solid #94a3b8;border-top-color:#047857;border-radius:50%;animation:spin 0.8s linear infinite;"></span>
      Reasoning over official gazette database…
    </p>`
  );
  chatLog.appendChild(typingBubble);
  chatLog.scrollTop = chatLog.scrollHeight;

  try {
    const res = await API.sendChatMessage({ message: text, session_id: currentSessionId });
    typingBubble.remove();

    // Render AI reply
    const replyHtml = renderMarkdown(res.reply || "No reply available.");

    // Note: Rate limit message usage is commented out for now as per task specifications
    /*
    const footerNote = res.requires_auth
      ? `<div style="margin-top:12px;padding:10px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;font-size:12px;color:#991b1b;">
          <strong>Guest limit reached:</strong> <a href="login.html" style="color:#b91c1c;font-weight:700;text-decoration:underline;">Sign in</a> or <a href="signup.html" style="color:#b91c1c;font-weight:700;text-decoration:underline;">Create free account</a> for unlimited AI guidance.
        </div>`
      : "";
    */

    chatLog.appendChild(createBubble("ai", replyHtml));

    // Update cited sources panel
    renderSources(res.schemes || []);

    // Update suggestions
    if (res.suggestions && res.suggestions.length > 0) {
      renderSuggestions(res.suggestions);
    }
  } catch (err) {
    console.error("Chat error:", err);
    typingBubble.remove();
    chatLog.appendChild(
      createBubble(
        "ai",
        `<p style="color:#dc2626;">I could not reach the scheme database at this moment. Please check your connection and retry.</p>`
      )
    );
  }

  chatLog.scrollTop = chatLog.scrollHeight;
}

// Start a fresh new chat session
async function startNewChat() {
  if (isResetting) return;
  const newChatBtn = document.getElementById("newChatBtn");
  const chatLog = document.getElementById("chatLog");
  const input = document.getElementById("chatInput");

  // Prevent duplicate clicks
  isResetting = true;
  if (newChatBtn) {
    newChatBtn.disabled = true;
    newChatBtn.textContent = "Starting new chat…";
  }

  const prevSessionId = currentSessionId;

  try {
    // 1. Reset profile / entity context on the backend for the previous session if available
    if (prevSessionId && typeof API.resetChatSession === "function") {
      try {
        await API.resetChatSession(prevSessionId);
      } catch (backendErr) {
        console.warn("Backend reset endpoint notice:", backendErr);
      }
    }

    // 2. Generate a new session_id and update localStorage
    const newSessionId = (typeof createNewGuestSessionId === "function")
      ? createNewGuestSessionId()
      : ("guest_" + Math.random().toString(36).substring(2, 11) + "_" + Date.now().toString(36));
    
    currentSessionId = newSessionId;

    // 3. Clear displayed messages and restore initial welcome greeting
    if (chatLog) {
      chatLog.innerHTML = WELCOME_INTRO_HTML;
      chatLog.scrollTop = 0;
    }

    // 4. Reset input and panels
    if (input) input.value = "";
    renderSources([]);
    
    // 5. Restore default prompts panel if suggestions were replaced
    const promptsPanel = document.querySelector(".prompts-panel");
    if (promptsPanel) {
      promptsPanel.innerHTML = `
        <h2>Try a grounded question</h2>
        <button type="button" class="prompt-chip"
          data-prompt="Am I eligible for PM-KISAN if I own 1.2 acres in Uttar Pradesh?">PM-KISAN eligibility on 1.2
          acres</button>
        <button type="button" class="prompt-chip" data-prompt="What documents do I need for Atal Pension Yojana?">APY
          document checklist</button>
        <button type="button" class="prompt-chip" data-prompt="Is Ayushman Bharat free at empaneled hospitals?">PM-JAY
          hospital charges</button>
        <button type="button" class="prompt-chip"
          data-prompt="Can someone on WhatsApp charge me to apply for PMMVY?">Fraud check on agents</button>
        <div class="panel-note">
          Answers cite gazette rules. Always apply only on the official portal linked in the reply.
        </div>
      `;
      promptsPanel.querySelectorAll(".prompt-chip").forEach((btn) => {
        btn.addEventListener("click", () => {
          askQuestion(btn.getAttribute("data-prompt"));
        });
      });
    }

    if (typeof showToast === "function") {
      showToast("Started a new chat session", "info");
    }
  } catch (err) {
    console.error("Failed to start new chat:", err);
    if (typeof showToast === "function") {
      showToast("Could not start a new chat. Please try again.", "error");
    }
  } finally {
    isResetting = false;
    if (newChatBtn) {
      newChatBtn.disabled = false;
      newChatBtn.textContent = "+ New Chat";
    }
  }
}

// Load previous chat history if available
async function loadChatHistory() {
  const chatLog = document.getElementById("chatLog");
  if (!chatLog) return;

  // Always initialize with welcome intro card
  chatLog.innerHTML = WELCOME_INTRO_HTML;

  try {
    const history = await API.getChatHistory(currentSessionId);

    if (history && Array.isArray(history.messages) && history.messages.length > 0) {
      history.messages.forEach((msg) => {
        const role = (msg.sender === "user" || msg.role === "user") ? "user" : "ai";
        const content = msg.message || msg.content || "";
        if (content && content.trim()) {
          chatLog.appendChild(createBubble(role, renderMarkdown(content)));
        }
      });
      chatLog.scrollTop = chatLog.scrollHeight;
    }
  } catch (err) {
    console.warn("Could not retrieve session chat history:", err);
  }
}

function initAssistant() {
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  const newChatBtn = document.getElementById("newChatBtn");

  if (form && input) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      askQuestion(text);
    });
  }

  if (newChatBtn) {
    newChatBtn.addEventListener("click", startNewChat);
  }

  document.querySelectorAll(".prompt-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      askQuestion(btn.getAttribute("data-prompt"));
    });
  });

  loadChatHistory().then(() => {
    const preset = new URLSearchParams(window.location.search).get("q");
    if (preset) {
      askQuestion(preset);
    }
  });
}

document.addEventListener("DOMContentLoaded", initAssistant);

