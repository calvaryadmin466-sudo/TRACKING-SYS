// Bootstrap: auth gate + professional sign-in, then mount the app shell.
import { get, getToken, clearToken, login as apiLogin } from "./api.js";
import { session } from "./store.js";
import { mountShell } from "./router.js";
import { icon, refreshIcons, qs } from "./ui.js";

function loginView() {
  const root = qs("#app-root");
  root.innerHTML = `
    <div class="login">
      <form class="login-card" id="login-form" novalidate>
        <div class="login-brand">
          <div class="logo" style="width:38px;height:38px">${icon("navigation", "i-lg")}</div>
          <div><b style="font-size:18px">FleetTrack</b><div class="dim" style="font-size:12px">GPS &amp; Video Tracking</div></div>
        </div>
        <h3 style="margin-bottom:4px">Sign in</h3>
        <p class="muted" style="margin:0 0 18px;font-size:13px">Access your fleet operations console</p>
        <div class="field-group">
          <label class="field" for="email">Email</label>
          <div class="input-icon">${icon("mail")}<input class="input" id="email" type="email" autocomplete="username" placeholder="you@company.com" required></div>
        </div>
        <div class="field-group">
          <label class="field" for="password">Password</label>
          <div class="input-icon pw">${icon("lock")}
            <input class="input" id="password" type="password" autocomplete="current-password" placeholder="••••••••" required>
            <button type="button" class="toggle" id="pw-toggle" aria-label="Show password">${icon("eye")}</button>
          </div>
        </div>
        <div id="login-error" class="badge offline" style="display:none;width:100%;justify-content:flex-start;margin-bottom:12px"></div>
        <button class="btn primary" id="login-btn" type="submit" style="width:100%">Sign in</button>
      </form>
    </div>`;
  refreshIcons(root);

  const form = qs("#login-form"), errEl = qs("#login-error"), btn = qs("#login-btn");
  const pw = qs("#password");
  qs("#pw-toggle").addEventListener("click", () => {
    const show = pw.type === "password"; pw.type = show ? "text" : "password";
    qs("#pw-toggle").innerHTML = icon(show ? "eye-off" : "eye"); refreshIcons(qs("#pw-toggle").parentElement);
  });
  const showErr = (m) => { errEl.style.display = "flex"; errEl.textContent = m; };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errEl.style.display = "none";
    const email = qs("#email").value.trim(), password = pw.value;
    if (!email || !password) { showErr("Enter your email and password."); return; }
    btn.disabled = true; btn.innerHTML = `<span class="spinner" style="width:16px;height:16px;border-width:2px"></span> Signing in…`;
    try {
      session.user = await apiLogin(email, password);
      location.hash = "#/";
      mountShell();
    } catch (ex) {
      showErr(ex.status === 429 ? "Too many attempts. Please wait and try again." : (ex.detail || "Invalid credentials."));
      btn.disabled = false; btn.textContent = "Sign in";
    }
  });
}

async function boot() {
  if (getToken()) {
    try {
      const me = await get("/api/auth/me");
      session.user = { id: me.user_id, email: me.email, role: me.role, organization_id: me.organization_id };
      if (!location.hash || location.hash === "#/login") location.hash = "#/";
      mountShell();
      return;
    } catch { clearToken(); }
  }
  loginView();
}

boot();
