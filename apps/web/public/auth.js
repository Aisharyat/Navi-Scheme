// ============================================================================
// NAVI SCHEME — Authentication Handling (Citizen & Admin)
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("loginForm");
  const signupForm = document.getElementById("signupForm");

  // Populate state dropdown in signup form if available
  const statePrefSelect = document.getElementById("statePref");
  if (statePrefSelect) {
    API.getTaxonomies()
      .then((data) => {
        if (data && data.states && data.states.length > 0) {
          statePrefSelect.innerHTML = `<option value="All India">All India (Central + States)</option>` +
            data.states
              .filter((s) => s !== "All India")
              .map((s) => `<option value="${s}">${s}</option>`)
              .join("");
        }
      })
      .catch(() => {});
  }

  // --------------------------------------------------------------------------
  // Citizen & Admin Login Handler
  // --------------------------------------------------------------------------
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorBox = document.getElementById("authErrorBox");
      const submitBtn = document.getElementById("loginSubmitBtn");
      if (errorBox) errorBox.style.display = "none";

      const idInput = document.getElementById("loginId");
      const passInput = document.getElementById("loginPass");

      const email = idInput.value.trim();
      const password = passInput.value;

      if (!email || !password) {
        if (errorBox) {
          errorBox.textContent = "Please enter both email/mobile and password.";
          errorBox.style.display = "block";
        }
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Signing in…";
      }

      try {
        let authResponse = null;
        let isAdminUser = false;

        // Check if admin login should be attempted first
        if (email.toLowerCase().includes("admin") || email.endsWith(".gov.in")) {
          try {
            authResponse = await API.loginAdmin({ email, password });
            isAdminUser = true;
          } catch (adminErr) {
            // If admin fails, attempt citizen login
            authResponse = await API.loginCitizen({ email, password });
          }
        } else {
          try {
            authResponse = await API.loginCitizen({ email, password });
          } catch (citErr) {
            // Attempt admin as fallback
            try {
              authResponse = await API.loginAdmin({ email, password });
              isAdminUser = true;
            } catch {
              throw citErr;
            }
          }
        }

        if (authResponse && authResponse.access_token) {
          const sessionPayload = {
            id: authResponse.user_id,
            email: authResponse.email || email,
            full_name: authResponse.full_name || (isAdminUser ? "Administrator" : "Citizen"),
            role: authResponse.role || (isAdminUser ? "admin" : "citizen"),
          };

          setSession(sessionPayload, authResponse.access_token);
          showToast(`Welcome, ${sessionPayload.full_name}!`, "success");

          setTimeout(() => {
            if (sessionPayload.role === "admin") {
              window.location.href = "admin.html";
            } else {
              window.location.href = "tracker.html";
            }
          }, 400);
        }
      } catch (err) {
        console.error("Login failed:", err);
        if (errorBox) {
          errorBox.textContent = err.message || "Invalid credentials. Please check and retry.";
          errorBox.style.display = "block";
        }
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Sign in";
        }
      }
    });
  }

  // --------------------------------------------------------------------------
  // Citizen Registration Handler
  // --------------------------------------------------------------------------
  if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorBox = document.getElementById("authErrorBox");
      const submitBtn = document.getElementById("signupSubmitBtn");
      if (errorBox) errorBox.style.display = "none";

      const fullName = document.getElementById("fullName").value.trim();
      const email = document.getElementById("signupId").value.trim();
      const state = document.getElementById("statePref") ? document.getElementById("statePref").value : "All India";
      const password = document.getElementById("signupPass").value;

      if (!fullName || !email || !password) {
        if (errorBox) {
          errorBox.textContent = "Please fill in all required fields.";
          errorBox.style.display = "block";
        }
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Creating Account…";
      }

      try {
        const payload = {
          full_name: fullName,
          email,
          password,
          state: state || "All India",
          role: "citizen",
        };

        const res = await API.registerCitizen(payload);

        if (res && res.access_token) {
          const sessionPayload = {
            id: res.user_id,
            email: res.email || email,
            full_name: res.full_name || fullName,
            role: res.role || "citizen",
            state,
          };

          setSession(sessionPayload, res.access_token);
          showToast("Account created successfully! Welcome to NAVI SCHEME.", "success");

          setTimeout(() => {
            window.location.href = "index.html";
          }, 500);
        }
      } catch (err) {
        console.error("Signup failed:", err);
        if (errorBox) {
          errorBox.textContent = err.message || "Could not register account. Email might already be in use.";
          errorBox.style.display = "block";
        }
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Create account";
        }
      }
    });
  }
});
