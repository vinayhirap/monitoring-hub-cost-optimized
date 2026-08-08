// src/api/api.js
const BASE = "";

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

// ── Live real AWS data ─────────────────────────────────────────
export const getLiveAccounts  = ()   => apiFetch("/api/live/accounts");
export const getLiveEC2       = (id) => apiFetch(`/api/live/ec2/${id}`);
export const getLiveRDS       = (id) => apiFetch(`/api/live/rds/${id}`);
export const getLiveLambda    = (id) => apiFetch(`/api/live/lambda/${id}`);
export const getLiveEC2Metrics= (instanceId, region) =>
  apiFetch(`/api/live/metrics/ec2/${instanceId}${region ? `?region=${region}` : ""}`);

// ── Admin ─────────────────────────────────────────────────────
export const getAccounts      = ()   => apiFetch("/api/admin/accounts");
export const addAccount       = (data) => apiFetch("/api/admin/accounts", { method:"POST", body: JSON.stringify(data) });
export const discoverAccount  = (id)   => apiFetch(`/api/admin/accounts/${id}/discover`, { method:"POST" });
export const testRole         = (data) => apiFetch("/api/admin/accounts/test-role", { method:"POST", body: JSON.stringify(data) });

// ── Alerts ────────────────────────────────────────────────────
export const getAlerts = () => apiFetch("/api/alerts/open");
export const acknowledgeAlert = (id) => apiFetch(`/api/alerts/${id}/ack`,     { method: "PATCH" });
export const resolveAlert     = (id) => apiFetch(`/api/alerts/${id}/resolve`,  { method: "PATCH" });
export const muteAlert        = (id) => apiFetch(`/api/alerts/${id}/mute`,     { method: "PATCH" });

// ── Audit logs ────────────────────────────────────────────────
export const getAuditLogs     = (limit=100) => apiFetch(`/api/audit-logs?limit=${limit}`);

// ── Auth ──────────────────────────────────────────────────────
export const login = (username, password) =>
  apiFetch("/api/auth/login", { method:"POST", body: JSON.stringify({ username, password }) });