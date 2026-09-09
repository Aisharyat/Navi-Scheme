// ============================================================================
// NAVI SCHEME — Global Site Infrastructure & Unified API Client
// ============================================================================

const STORAGE_KEYS = {
  AUTH_TOKEN: "navi_auth_token",
  USER_SESSION: "navi_user_session",
  GUEST_SESSION_ID: "navi_guest_session_id",
  LOCAL_SAVED_APPS: "navi_local_saved_apps",
  TAXONOMIES_CACHE: "navi_taxonomies_cache",
};

// Generate or retrieve persistent guest session ID
function getGuestSessionId() {
  let sessionId = localStorage.getItem(STORAGE_KEYS.GUEST_SESSION_ID);
  if (!sessionId) {
    sessionId = "guest_" + Math.random().toString(36).substring(2, 11) + "_" + Date.now().toString(36);
    localStorage.setItem(STORAGE_KEYS.GUEST_SESSION_ID, sessionId);
  }
  return sessionId;
}

// Generate a brand new guest session ID and update storage
function createNewGuestSessionId() {
  const sessionId = "guest_" + Math.random().toString(36).substring(2, 11) + "_" + Date.now().toString(36);
  localStorage.setItem(STORAGE_KEYS.GUEST_SESSION_ID, sessionId);
  return sessionId;
}

// ----------------------------------------------------------------------------
// Local Storage Helpers
// ----------------------------------------------------------------------------
function readJSON(key, fallback = null) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (err) {
    console.warn("[Storage] Error reading", key, err);
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    console.warn("[Storage] Error writing", key, err);
  }
}

// ----------------------------------------------------------------------------
// Session & Auth State Management
// ----------------------------------------------------------------------------
function getAuthToken() {
  return localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN) || "";
}

function getSession() {
  return readJSON(STORAGE_KEYS.USER_SESSION, null);
}

function setSession(sessionData, token = null) {
  if (token) {
    localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, token);
  }
  writeJSON(STORAGE_KEYS.USER_SESSION, sessionData);
}

function clearSession() {
  localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.USER_SESSION);
}

function isLoggedIn() {
  return !!getAuthToken() && !!getSession();
}

function isAdmin() {
  const session = getSession();
  return session && session.role === "admin";
}

// ----------------------------------------------------------------------------
const API_BASE_URL = (() => {
  if (typeof window === "undefined" || !window.location) return "http://127.0.0.1:8000";
  const origin = window.location.origin;
  if (!origin || origin === "null" || window.location.protocol === "file:") {
    return "http://127.0.0.1:8000";
  }
  return origin;
})();

async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
  const token = getAuthToken();

  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  try {
    let response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
      });
    } catch (netErr) {
      // Fallback attempt to standard local backend port if running on different dev port
      if (!url.includes("127.0.0.1:8000") && !url.includes("localhost:8000")) {
        const fallbackUrl = `http://127.0.0.1:8000${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
        response = await fetch(fallbackUrl, {
          ...options,
          headers,
        });
      } else {
        throw netErr;
      }
    }

    const isJson = (response.headers.get("content-type") || "").includes("application/json");
    const data = isJson ? await response.json() : await response.text();

    if (!response.ok) {
      const errorMessage =
        (typeof data === "object" && (data.detail || data.message || data.error)) ||
        `Request failed with status ${response.status}`;
      const err = new Error(errorMessage);
      err.status = response.status;
      err.data = data;
      throw err;
    }

    return data;
  } catch (error) {
    console.error(`[API Error] ${options.method || "GET"} ${endpoint}:`, error);
    throw error;
  }
}

const API = {
  // Public Schemes
  getTaxonomies: async () => {
    const cached = readJSON(STORAGE_KEYS.TAXONOMIES_CACHE);
    if (cached) return cached;
    const res = await apiRequest("/api/taxonomies");
    writeJSON(STORAGE_KEYS.TAXONOMIES_CACHE, res);
    return res;
  },

  getSchemes: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "" && v !== "All India (Central + States)" && v !== "✓ All Categories Selected" && v !== "All") {
        query.append(k, v);
      }
    });
    const qs = query.toString();
    return apiRequest(`/api/schemes${qs ? `?${qs}` : ""}`);
  },

  getScheme: (identifier) => apiRequest(`/api/schemes/${encodeURIComponent(identifier)}`),

  matchEligibility: (profileData) =>
    apiRequest("/api/eligibility/match", {
      method: "POST",
      body: JSON.stringify(profileData),
    }),

  explainScheme: (identifier, payload = {}) =>
    apiRequest(`/api/schemes/${encodeURIComponent(identifier)}/explain`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Grounded Conversational AI Chat
  sendChatMessage: (payload) => {
    const session = getSession();
    const sessionProfile = (session && typeof session === "object") ? {
      age: session.age,
      gender: session.gender,
      state: session.state,
      category: session.category,
      annual_income: session.annual_income,
      occupation: session.occupation,
    } : {};

    return apiRequest("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: getGuestSessionId(),
        language: "en",
        ...sessionProfile,
        ...payload,
      }),
    });
  },

  getChatHistory: (sessionId) =>
    apiRequest(`/api/chat/history/${encodeURIComponent(sessionId || getGuestSessionId())}`),

  resetChatSession: (sessionId) =>
    apiRequest(`/api/chat/${encodeURIComponent(sessionId || getGuestSessionId())}/reset`, {
      method: "POST",
    }),

  submitFeedback: (payload) =>
    apiRequest("/api/feedback", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Citizen Authentication & Profile
  registerCitizen: (payload) =>
    apiRequest("/api/user/auth/register", {
      method: "POST",
      body: JSON.stringify({
        session_id: getGuestSessionId(),
        ...payload,
      }),
    }),

  loginCitizen: (payload) =>
    apiRequest("/api/user/auth/login", {
      method: "POST",
      body: JSON.stringify({
        session_id: getGuestSessionId(),
        ...payload,
      }),
    }),

  getCitizenProfile: () => apiRequest("/api/user/profile"),
  updateCitizenProfile: (payload) =>
    apiRequest("/api/user/profile", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  // Citizen Saved Bookmarks
  getSavedSchemes: () => apiRequest("/api/user/saved-schemes"),
  saveScheme: (schemeId) =>
    apiRequest(`/api/user/saved-schemes/${encodeURIComponent(schemeId)}`, {
      method: "POST",
    }),
  removeSavedScheme: (schemeId) =>
    apiRequest(`/api/user/saved-schemes/${encodeURIComponent(schemeId)}`, {
      method: "DELETE",
    }),

  // Application Tracker
  getApplications: () => apiRequest("/api/user/applications"),
  updateApplicationStatus: (schemeId, status, notes = "") =>
    apiRequest(`/api/user/applications/${encodeURIComponent(schemeId)}`, {
      method: "POST",
      body: JSON.stringify({ status, notes }),
    }),

  // Admin APIs
  loginAdmin: (payload) =>
    apiRequest("/api/admin/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getAdminProfile: () => apiRequest("/api/admin/auth/me"),
  getAdminAnalytics: () => apiRequest("/api/admin/analytics"),
  getAdminPipelineHealth: () => apiRequest("/api/admin/pipeline/health"),
  getAdminSchemes: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") query.append(k, v);
    });
    const qs = query.toString();
    return apiRequest(`/api/admin/schemes${qs ? `?${qs}` : ""}`);
  },
  publishScheme: (schemeId) =>
    apiRequest(`/api/admin/schemes/${encodeURIComponent(schemeId)}/publish`, {
      method: "POST",
    }),
  createScheme: (payload) =>
    apiRequest("/api/admin/schemes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// ----------------------------------------------------------------------------
// Local Storage Bookmark Fallback (for guests)
// ----------------------------------------------------------------------------
function getLocalSavedApps() {
  return readJSON(STORAGE_KEYS.LOCAL_SAVED_APPS, []);
}

function isLocalSaved(schemeId) {
  const list = getLocalSavedApps();
  return list.some((item) => (typeof item === "string" ? item === schemeId : item.id === schemeId));
}

function toggleLocalSaved(scheme) {
  const list = getLocalSavedApps();
  const id = typeof scheme === "string" ? scheme : scheme.id;
  const index = list.findIndex((item) => (typeof item === "string" ? item === id : item.id === id));
  if (index >= 0) {
    list.splice(index, 1);
    writeJSON(STORAGE_KEYS.LOCAL_SAVED_APPS, list);
    return false;
  } else {
    const item = typeof scheme === "string" ? { id: scheme, savedAt: new Date().toISOString() } : scheme;
    list.unshift(item);
    writeJSON(STORAGE_KEYS.LOCAL_SAVED_APPS, list);
    return true;
  }
}

// ----------------------------------------------------------------------------
// UI Toast Notification System
// ----------------------------------------------------------------------------
function showToast(message, type = "info") {
  let container = document.getElementById("naviToastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "naviToastContainer";
    container.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 99999;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: 380px;
      pointer-events: none;
    `;
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.style.cssText = `
    pointer-events: auto;
    background: ${type === "success" ? "#064e3b" : type === "error" ? "#7f1d1d" : "#0f172a"};
    color: #fff;
    padding: 12px 18px;
    border-radius: 8px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    font-size: 13.5px;
    font-weight: 500;
    line-height: 1.4;
    display: flex;
    align-items: center;
    gap: 10px;
    border-left: 4px solid ${type === "success" ? "#10b981" : type === "error" ? "#ef4444" : "#3b82f6"};
    animation: toastSlideIn 0.3s ease-out;
  `;

  const icon =
    type === "success"
      ? "✓"
      : type === "error"
        ? "✕"
        : "ℹ";

  toast.innerHTML = `<span><strong>${icon}</strong></span> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ----------------------------------------------------------------------------
// Dynamic Navigation Chrome Header
// ----------------------------------------------------------------------------
function navItems(active) {
  const items = [
    { id: "discover", href: "index.html", label: "Discover &amp; Match" },
    { id: "assistant", href: "assistant.html", label: "AI Assistant" },
    { id: "tracker", href: "tracker.html", label: "Scheme Tracker" },
  ];
  return items
    .map(
      (item) =>
        `<a class="nav-link${item.id === active ? " active" : ""}" href="${item.href}">${item.label}</a>`
    )
    .join("");
}

function renderChrome() {
  let mount = document.getElementById("naviChromeMount") || document.querySelector("[data-chrome]");
  if (!mount) return;
  const active = mount.getAttribute("data-chrome") || mount.getAttribute("data-active") || "";
  mount.id = "naviChromeMount";
  mount.setAttribute("data-active", active);

  const session = getSession();
  const authenticated = isLoggedIn();
  const userIsAdmin = isAdmin();

  let authButtonHtml = "";
  if (authenticated && session) {
    const displayName = session.full_name || session.name || session.email || "Citizen";
    const initials = displayName.split(" ").map((n) => n[0]).join("").substring(0, 2).toUpperCase() || "C";
    const roleBadge = userIsAdmin ? `<span class="badge" style="background:#dc2626;color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;margin-left:4px;">ADMIN</span>` : "";
    authButtonHtml = `
      <div class="user-pill">
        <span class="user-avatar-badge" style="width:28px;height:28px;border-radius:50%;background:#047857;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;">${initials}</span>
        <span class="user-name-text" title="${displayName}">${displayName}</span>
        ${roleBadge}
        <button type="button" class="btn btn-ghost js-signout" style="padding:5px 10px;font-size:11.5px;">Sign out</button>
      </div>
    `;
  } else {
    authButtonHtml = `<a class="btn btn-signin" href="login.html">Sign in</a>`;
  }

  const adminLinkHtml = userIsAdmin
    ? `<a class="btn btn-ghost${active === "admin" ? " is-current" : ""}" href="admin.html" style="color:#dc2626;font-weight:700;font-size:12px;padding:6px 12px;">Admin Console</a>`
    : `<a class="btn btn-ghost${active === "admin" ? " is-current" : ""}" href="admin.html" style="font-size:12px;padding:6px 12px;">Admin</a>`;

  mount.innerHTML = `
  <div class="topbar">
    <div class="topbar-inner">
      <div class="topbar-left">
        <svg class="shield-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <span class="beta">BETA</span>
      </div>
      <div class="topbar-right">
        <span class="topbar-strong">✓ Verified database of 3,400+ Central &amp; State Schemes</span>
      </div>
    </div>
  </div>
  <header class="header">
    <div class="header-inner">
      <a class="brand" href="index.html">
        <img src="logo.png" alt="NAVI SCHEME emblem" class="brand-logo" width="44" height="44" />
        <span class="brand-text">
          <span class="brand-name">NAVI SCHEME</span>
          <span class="brand-tagline">NAVIGATE TO RIGHT SCHEME</span>
        </span>
      </a>
      <nav class="nav" aria-label="Primary">
        ${navItems(active)}
        <span class="trust-pill"><span class="trust-dot"></span>Official Portals Only</span>
      </nav>
      <div class="header-actions">
        ${adminLinkHtml}
        ${authButtonHtml}
        <button type="button" class="menu-toggle" aria-label="Open menu" aria-expanded="false">
          <span></span><span></span><span></span>
        </button>
      </div>
    </div>
    <div class="mobile-drawer" hidden>
      <nav class="mobile-nav" aria-label="Mobile">
        ${navItems(active)}
        <a class="nav-link${active === "admin" ? " active" : ""}" href="admin.html">Admin Console</a>
        ${authenticated && session
      ? `<a class="nav-link js-signout" href="#">Sign out (${session.email})</a>`
      : `<a class="nav-link${active === "auth" ? " active" : ""}" href="login.html">Sign in</a>`
    }
        <span class="trust-pill"><span class="trust-dot"></span>Official Portals Only</span>
      </nav>
    </div>
  </header>`;

  // Bind signout actions with instant state transition
  document.querySelectorAll(".js-signout").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      clearSession();
      renderChrome();
      showToast("Signed out successfully", "info");
      if (window.location.pathname.includes("tracker.html") || window.location.pathname.includes("admin.html")) {
        setTimeout(() => {
          window.location.href = "index.html";
        }, 300);
      }
    });
  });

  // Mobile menu toggle
  const toggle = document.querySelector(".menu-toggle");
  const drawer = document.querySelector(".mobile-drawer");
  if (toggle && drawer) {
    toggle.addEventListener("click", () => {
      const open = drawer.hasAttribute("hidden");
      if (open) drawer.removeAttribute("hidden");
      else drawer.setAttribute("hidden", "");
      toggle.setAttribute("aria-expanded", String(open));
      toggle.classList.toggle("open", open);
    });
  }
}

// Auto-run chrome on DOM ready
document.addEventListener("DOMContentLoaded", renderChrome);
