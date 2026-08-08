// src/pages/Login.jsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import "./Login.css";

export default function Login() {
  const { login } = useAuth();
  const navigate   = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [showPw,   setShowPw]   = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Username and password are required.");
      return;
    }
    setLoading(true);
    setError("");
    await new Promise(r => setTimeout(r, 400));
    const ok = login(username.trim(), password);
    setLoading(false);
    if (ok) {
      navigate("/overview", { replace: true });
    } else {
      setError("Invalid username or password.");
    }
  }

  return (
    <div className="login-root">
      <div className="login-grid" aria-hidden="true">
        {Array.from({ length: 80 }).map((_, i) => (
          <div key={i} className="login-grid-cell" />
        ))}
      </div>
      <div className="login-blob login-blob-1" aria-hidden="true" />
      <div className="login-blob login-blob-2" aria-hidden="true" />

      <div className="login-card">
        <div className="login-brand">
          <div className="login-logo">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
              <rect x="2" y="2" width="32" height="32" rx="8" fill="rgba(0,199,255,0.12)" stroke="rgba(0,199,255,0.4)" strokeWidth="1.5"/>
              <path d="M10 24 L18 12 L26 24" stroke="#00c7ff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M13 20 L23 20" stroke="#00e5a0" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <div className="login-brand-name">ASLOps</div>
            <div className="login-brand-sub">Monitoring Dashboard</div>
          </div>
        </div>

        <h1 className="login-title">Welcome back</h1>
        <p className="login-desc">Sign in to continue to your cloud monitoring hub</p>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="login-field">
            <label htmlFor="username">Username</label>
            <div className="login-input-wrap">
              <span className="login-input-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </span>
              <input
                id="username"
                type="text"
                className="login-input"
                placeholder="Enter username"
                value={username}
                onChange={e => { setUsername(e.target.value); setError(""); }}
                autoComplete="username"
                autoFocus
                disabled={loading}
              />
            </div>
          </div>

          <div className="login-field">
            <label htmlFor="password">Password</label>
            <div className="login-input-wrap">
              <span className="login-input-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </span>
              <input
                id="password"
                type={showPw ? "text" : "password"}
                className="login-input"
                placeholder="Enter password"
                value={password}
                onChange={e => { setPassword(e.target.value); setError(""); }}
                autoComplete="current-password"
                disabled={loading}
              />
              <button
                type="button"
                className="login-toggle-pw"
                onClick={() => setShowPw(v => !v)}
                tabIndex={-1}
              >
                {showPw ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
          </div>

          {error && (
            <div className="login-error" role="alert">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              {error}
            </div>
          )}

          <button
            type="submit"
            className={`login-btn ${loading ? "login-btn-loading" : ""}`}
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="login-spinner" />
                Authenticating…
              </>
            ) : (
              "Sign In →"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
