import { getAuthToken } from './api';

const listeners = new Set();
let socket = null;
let reconnectTimer = null;
let retries = 0;

const MAX_RETRIES = 8;
const RECONNECT_MS = 5000;

export function getTaskWebSocketUrl() {
  const token = getAuthToken();
  if (!token) return null;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Use proxied path so Vite dev server can proxy WS to backend (/api -> http://localhost:8000)
  return `${protocol}//${window.location.host}/ws/${token}`;
}

function emit(data) {
  listeners.forEach((callback) => {
    try {
      callback(data);
    } catch (err) {
      console.error('Task WebSocket listener failed', err);
    }
  });
}

function scheduleReconnect() {
  if (listeners.size === 0 || !getAuthToken()) return;
  if (retries >= MAX_RETRIES) return;

  retries += 1;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_MS);
}

function connect() {
  if (!getAuthToken()) return;
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const url = getTaskWebSocketUrl();
  if (!url) return;

  socket = new WebSocket(url);

  socket.onopen = () => {
    retries = 0;
  };

  socket.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data);
      emit(parsed);
      window.dispatchEvent(new CustomEvent('ws_message', { detail: parsed }));
    } catch (err) {
      console.error('Failed to parse task WebSocket message', err);
    }
  };

  socket.onerror = () => {
    // onclose handles reconnect
  };

  socket.onclose = () => {
    socket = null;
    scheduleReconnect();
  };
}

export function subscribeTaskUpdates(callback) {
  listeners.add(callback);
  connect();

  return () => {
    listeners.delete(callback);
    if (listeners.size === 0) {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (socket) {
        socket.close();
        socket = null;
      }
      retries = 0;
    }
  };
}
