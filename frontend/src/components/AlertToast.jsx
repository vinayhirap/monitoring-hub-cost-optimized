// src/components/AlertToast.jsx
import { useEffect, useRef, useState } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

const SOUND_URL = "https://actions.google.com/sounds/v1/alarms/alarm_clock.ogg";

export default function AlertToast() {
  const [toasts, setToasts]       = useState([]);
  const audioRef                  = useRef(null);
  const { lastMessage: alertMsg } = useWebSocket("alerts");

  // Init audio
  useEffect(() => {
    audioRef.current = new Audio(SOUND_URL);
    audioRef.current.volume = 0.7;
  }, []);

  // React to new WS alert
  useEffect(() => {
    if (!alertMsg || alertMsg.type !== "new_alert") return;
    const toast = {
      id:        Date.now(),
      severity:  alertMsg.severity  || "WARNING",
      metric:    alertMsg.metric    || "Unknown",
      value:     alertMsg.value     ?? 0,
      threshold: alertMsg.threshold ?? 0,
      account_id:alertMsg.account_id,
    };
    setToasts(prev => [toast, ...prev].slice(0, 5));

    // Beep on CRITICAL
    if ((alertMsg.severity || "").toUpperCase() === "CRITICAL") {
      try { audioRef.current?.play().catch(() => {}); } catch {}
    }

    // Auto-dismiss after 8s
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toast.id));
    }, 8000);
  }, [alertMsg]);

  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24,
      display: "flex", flexDirection: "column", gap: 10,
      zIndex: 9999, maxWidth: 380,
    }}>
      {toasts.map(t => (
        <ToastItem key={t.id} toast={t} onClose={() => setToasts(p => p.filter(x => x.id !== t.id))} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onClose }) {
  const isCrit  = toast.severity === "CRITICAL";
  const color   = isCrit ? "#ff4d6d" : "#ffc940";
  const bg      = isCrit ? "rgba(255,77,109,0.12)" : "rgba(255,201,64,0.10)";
  const border  = isCrit ? "rgba(255,77,109,0.4)"  : "rgba(255,201,64,0.3)";

  return (
    <div style={{
      background: bg, border: `1px solid ${border}`,
      borderRadius: 10, padding: "14px 16px",
      display: "flex", gap: 12, alignItems: "flex-start",
      boxShadow: `0 4px 24px ${color}22`,
      animation: "slideIn .25s ease",
    }}>
      <div style={{ fontSize: 22, flexShrink: 0 }}>{isCrit ? "🚨" : "⚠️"}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: 14, color, marginBottom: 3 }}>
          {toast.severity} ALERT
        </div>
        <div style={{ fontSize: 13, color: "#dce6f5", marginBottom: 2 }}>
          {toast.metric} — <strong>{toast.value}%</strong> (threshold: {toast.threshold}%)
        </div>
        <div style={{ fontSize: 11, color: "#4a5f80" }}>Account #{toast.account_id}</div>
      </div>
      <button onClick={onClose} style={{
        background: "none", border: "none", color: "#4a5f80",
        cursor: "pointer", fontSize: 16, padding: 0, lineHeight: 1,
      }}>✕</button>
    </div>
  );
}

