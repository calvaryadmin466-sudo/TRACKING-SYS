// API client: token handling, JSON helpers, consistent error objects.
const TOKEN_KEY = "ft_token";

export function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; } }
export function setToken(t) { try { localStorage.setItem(TOKEN_KEY, t); } catch {} }
export function clearToken() { try { localStorage.removeItem(TOKEN_KEY); } catch {} }

export class ApiError extends Error {
  constructor(status, detail) { super(typeof detail === "string" ? detail : "request failed"); this.status = status; this.detail = detail; }
}

export async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (opts.body !== undefined && !(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (getToken()) headers["Authorization"] = "Bearer " + getToken();
  const body = opts.body !== undefined && typeof opts.body !== "string" && !(opts.body instanceof FormData)
    ? JSON.stringify(opts.body) : opts.body;
  let res;
  try {
    res = await fetch(path, { ...opts, headers, body });
  } catch (e) {
    throw new ApiError(0, "network error — the server may be unreachable");
  }
  if (res.status === 401 && path !== "/api/auth/login") {
    clearToken();
    location.hash = "#/login";
    throw new ApiError(401, "session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail ?? detail; } catch {}
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const get = (p) => api(p);
export const post = (p, body) => api(p, { method: "POST", body });
export const patch = (p, body) => api(p, { method: "PATCH", body });
export const put = (p, body) => api(p, { method: "PUT", body });
export const del = (p) => api(p, { method: "DELETE" });

export async function login(email, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    let detail = "Invalid credentials";
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new ApiError(res.status, detail);
  }
  const data = await res.json();
  setToken(data.access_token);
  return data.user;
}
