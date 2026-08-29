import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const api = axios.create({ baseURL: API, timeout: 30000 });

export const SEVERITY_COLORS = {
    CRITICAL: "#e11d48",
    HIGH: "#ea580c",
    MEDIUM: "#d97706",
    LOW: "#059669",
    UNKNOWN: "#6b7280",
};

export const severityClass = (s) => {
    const m = { CRITICAL: "sev-critical", HIGH: "sev-high", MEDIUM: "sev-medium", LOW: "sev-low" };
    return m[s] || "sev-unknown";
};

export const roleFromStorage = () => localStorage.getItem("ner_role") || "AUTHORITY";
export const setRole = (r) => localStorage.setItem("ner_role", r);

// Offline report queue (localStorage-based)
const QKEY = "ner_offline_reports";
export const enqueueOffline = (r) => {
    const list = JSON.parse(localStorage.getItem(QKEY) || "[]");
    list.push({ ...r, client_uuid: r.client_uuid || crypto.randomUUID(), queued_at: new Date().toISOString() });
    localStorage.setItem(QKEY, JSON.stringify(list));
};
export const getOfflineQueue = () => JSON.parse(localStorage.getItem(QKEY) || "[]");
export const clearOfflineItem = (id) => {
    const list = JSON.parse(localStorage.getItem(QKEY) || "[]").filter((x) => x.client_uuid !== id);
    localStorage.setItem(QKEY, JSON.stringify(list));
};
export const flushOffline = async () => {
    const list = getOfflineQueue();
    for (const r of list) {
        try {
            await api.post("/reports", r);
            clearOfflineItem(r.client_uuid);
        } catch (e) { /* keep for next attempt */ }
    }
    return getOfflineQueue().length;
};
