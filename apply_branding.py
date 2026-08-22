#!/usr/bin/env python3
"""
apply_branding.py

Rebrands the app to "CloudOps" everywhere, with "AURIONPRO" (the company)
shown just above/before the CloudOps mark on the login page and sidebar.
Removes the "Monitoring Hub" name entirely.

Usage (from the ROOT of your monitoring-hub-cost-optimized checkout):

    python apply_branding.py

Safe to re-run: each replacement is skipped (with a note) if the new
text is already present, and flagged (not fatal) if neither the old nor
new text is found, so you can go check that one spot by hand.
Uses universal-newline text mode, so it works the same whether your
files are CRLF (Windows checkout) or LF.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Each entry: (file, description, old_text, new_text)
REPLACEMENTS = [
    (
        "frontend/src/components/Layout.jsx",
        "sidebar logo + brand text -> CloudOps mark, AURIONPRO above it",
        '''        <div className="sidebar-brand">
          <div className="sidebar-logo">
            <img src="/aslops_logo.png" alt="ASLOps" width="28" height="28" />
          </div>
          <div className="sidebar-brand-text">
            <div className="sidebar-brand-name">Aurionpro</div>
            <div className="sidebar-brand-sub">LeadNext<br />CloudOps</div>
          </div>
        </div>''',
        '''        <div className="sidebar-brand">
          <div className="sidebar-logo">
            <svg width="28" height="28" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg" aria-label="CloudOps">
              <rect width="512" height="512" rx="112" fill="#0b1220" />
              <g transform="translate(-891.82,2.79) scale(0.8064)">
                <path fill="#2bb3ac" d="M1331.98,222.58c41.39-41.42,103.91-48.88,152.93-22.35l53.65-53.65c-79.15-54.58-188.41-46.67-258.82,23.77-70.44,70.4-78.35,179.67-23.77,258.82l53.65-53.65c-26.53-49.02-19.07-111.55,22.35-152.93Z" />
                <path fill="#2bb3ac" d="M1567.06,457.66c70.44-70.44,78.35-179.7,23.73-258.85l-53.65,53.65c26.53,49.02,19.07,111.55-22.32,152.97-41.42,41.39-103.95,48.85-152.93,22.32l-53.65,53.65c79.15,54.62,188.38,46.71,258.82-23.73Z" />
              </g>
            </svg>
          </div>
          <div className="sidebar-brand-text">
            <div className="sidebar-brand-sub">AURIONPRO</div>
            <div className="sidebar-brand-name">CloudOps</div>
          </div>
        </div>''',
    ),
    (
        "frontend/src/pages/Login.jsx",
        "login desc text: drop 'monitoring hub' phrase",
        '"Sign in to continue to your cloud monitoring hub"',
        '"Sign in to continue to CloudOps"',
    ),
    (
        "frontend/src/pages/Login.jsx",
        "login brand block -> CloudOps mark, AURIONPRO above it",
        '''        <div className="login-brand">
          <img
            src="/aslops_logo.png"
            alt="ASLOps"
            className="login-logo-full"
          />
          <div className="login-brand-sub">Monitoring Hub</div>
        </div>''',
        '''        <div className="login-brand">
          <div className="login-brand-sub">AURIONPRO</div>
          <div className="login-logo-row">
            <svg width="34" height="34" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg" aria-label="CloudOps">
              <rect width="512" height="512" rx="112" fill="#0b1220" />
              <g transform="translate(-891.82,2.79) scale(0.8064)">
                <path fill="#2bb3ac" d="M1331.98,222.58c41.39-41.42,103.91-48.88,152.93-22.35l53.65-53.65c-79.15-54.58-188.41-46.67-258.82,23.77-70.44,70.4-78.35,179.67-23.77,258.82l53.65-53.65c-26.53-49.02-19.07-111.55,22.35-152.93Z" />
                <path fill="#2bb3ac" d="M1567.06,457.66c70.44-70.44,78.35-179.7,23.73-258.85l-53.65,53.65c26.53,49.02,19.07,111.55-22.32,152.97-41.42,41.39-103.95,48.85-152.93,22.32l-53.65,53.65c79.15,54.62,188.38,46.71,258.82-23.73Z" />
              </g>
            </svg>
            <span className="login-wordmark">Cloud<span className="login-wordmark-accent">Ops</span></span>
          </div>
        </div>''',
    ),
    (
        "frontend/src/pages/Login.css",
        "add wordmark/logo-row CSS after .login-logo-full",
        '''.login-logo-full {
  height: 34px;
  width: auto;
  flex-shrink: 0;
}''',
        '''.login-logo-full {
  height: 34px;
  width: auto;
  flex-shrink: 0;
}
.login-logo-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.login-wordmark {
  font-size: 22px;
  font-weight: 700;
  color: #e2e8f0;
  letter-spacing: 0.01em;
  font-family: 'JetBrains Mono', monospace;
}
.login-wordmark-accent {
  color: #2bb3ac;
}''',
    ),
    (
        "frontend/index.html",
        "page title + meta description",
        '''    <meta name="description" content="Aurionpro LeadNext Monitoring Hub — real-time cloud infrastructure monitoring and alerting." />
    <title>Monitoring Hub | Aurionpro LeadNext</title>''',
        '''    <meta name="description" content="Aurionpro CloudOps — real-time cloud infrastructure monitoring and alerting." />
    <title>CloudOps | Aurionpro</title>''',
    ),
    (
        "frontend/src/auth/AuthContext.jsx",
        "localStorage key (existing sessions will need to re-login once)",
        'const STORAGE_KEY = "aslops_auth";',
        'const STORAGE_KEY = "cloudops_auth";',
    ),
    (
        "frontend/src/components/icons.jsx",
        "cosmetic comment",
        "// Shared Feather-style line-icon set for Aurionpro LeadNext.",
        "// Shared Feather-style line-icon set for CloudOps.",
    ),
    (
        "frontend/src/index.css",
        "cosmetic comment",
        "  Aurionpro LeadNext design tokens.",
        "  CloudOps design tokens.",
    ),
    (
        "app/main.py",
        "FastAPI app title (shows in /docs Swagger UI)",
        'app = FastAPI(title="Monitoring Hub API", version="0.3.0", lifespan=lifespan)',
        'app = FastAPI(title="CloudOps API", version="0.3.0", lifespan=lifespan)',
    ),
    (
        "cleanup_backend.py",
        "cosmetic banner text in a dev script",
        '    print("  Monitoring Hub — Dead Endpoint Cleanup Script")',
        '    print("  CloudOps — Dead Endpoint Cleanup Script")',
    ),
]


def main():
    if not (ROOT / "app" / "db.py").exists():
        print("ERROR: run this from the root of the monitoring-hub-cost-optimized checkout.", file=sys.stderr)
        sys.exit(1)

    applied, skipped, missing = 0, 0, 0

    for rel_path, desc, old, new in REPLACEMENTS:
        path = ROOT / rel_path
        if not path.exists():
            print(f"[MISSING FILE] {rel_path} — {desc}")
            missing += 1
            continue

        text = path.read_text(encoding="utf-8")

        if new in text:
            print(f"[skip, already applied] {rel_path} — {desc}")
            skipped += 1
            continue

        if old not in text:
            print(f"[NOT FOUND, check manually] {rel_path} — {desc}")
            missing += 1
            continue

        text = text.replace(old, new, 1)
        path.write_text(text, encoding="utf-8")
        print(f"[applied] {rel_path} — {desc}")
        applied += 1

    print()
    print(f"Done. {applied} applied, {skipped} already applied, {missing} need manual check.")
    if missing:
        print("Some replacements didn't match — the surrounding code may have changed "
              "since this script was written. Nothing was left half-edited; check the "
              "flagged spots by hand.")

    print()
    print("Next: rebuild the frontend to see the changes:")
    print("    cd frontend && npm run build")


if __name__ == "__main__":
    main()
