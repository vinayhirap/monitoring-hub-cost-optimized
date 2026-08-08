// src/hooks/useWebSocket.js
// Singleton per channel — prevents duplicate connections across components
import { useEffect, useRef, useState } from "react";

const WS_BASE = `ws://${window.location.host}/ws`;
const _sockets    = {};          // channel → WebSocket
const _listeners  = {};          // channel → Set of {onMsg, onStatus}
const _reconnect  = {};          // channel → timeout handle

function getOrCreate(channel) {
  if (_sockets[channel] && _sockets[channel].readyState <= 1) return;

  const url    = `${WS_BASE}/${channel}`;
  const socket = new WebSocket(url);
  _sockets[channel] = socket;

  socket.onopen = () => {
    notifyStatus(channel, true);
    socket._ping = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 10000);
  };

  socket.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === "pong") return;
      notifyMsg(channel, data);
    } catch {}
  };

  socket.onclose = () => {
    clearInterval(socket._ping);
    notifyStatus(channel, false);
    delete _sockets[channel];
    // Reconnect after 4s
    clearTimeout(_reconnect[channel]);
    _reconnect[channel] = setTimeout(() => getOrCreate(channel), 1000);
  };

  socket.onerror = () => socket.close();
}

function notifyStatus(channel, connected) {
  (_listeners[channel] || new Set()).forEach(l => l.onStatus?.(connected));
}

function notifyMsg(channel, data) {
  (_listeners[channel] || new Set()).forEach(l => l.onMsg?.(data));
}

export function useWebSocket(channel) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const listenerRef = useRef(null);

  useEffect(() => {
    if (!_listeners[channel]) _listeners[channel] = new Set();

    const listener = {
      onMsg:    (data)      => setLastMessage(data),
      onStatus: (connected) => setIsConnected(connected),
    };
    listenerRef.current = listener;
    _listeners[channel].add(listener);

    // Set initial status
    const existing = _sockets[channel];
    if (existing?.readyState === WebSocket.OPEN) {
      setIsConnected(true);
    }

    // Create socket if needed (delayed to avoid StrictMode double-fire)
    const t = setTimeout(() => getOrCreate(channel), 50);

    return () => {
      clearTimeout(t);
      if (listenerRef.current) {
        _listeners[channel]?.delete(listenerRef.current);
      }
      // Don't close socket — other components may still use it
    };
  }, [channel]);

  return { isConnected, lastMessage };
}