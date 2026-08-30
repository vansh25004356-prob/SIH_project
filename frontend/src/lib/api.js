import axios from "axios";
import { supabase } from "./supabaseClient";

export const API = `${process.env.REACT_APP_API_BASE_URL || process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;
export const api = axios.create({ baseURL: API, timeout: 30000 });

api.interceptors.request.use(async (config) => {
    const { data } = await supabase.auth.getSession();
    const token = data?.session?.access_token;
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

export const auth = {
    signIn: (email, password) => supabase.auth.signInWithPassword({ email, password }),
    signUp: (email, password, fullName = "") => supabase.auth.signUp({ email, password, options: { data: { full_name: fullName } } }),
    signOut: () => supabase.auth.signOut(),
    session: () => supabase.auth.getSession(),
    onChange: (callback) => supabase.auth.onAuthStateChange(callback),
};

export async function uploadReportMedia(file, userId, reportId) {
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, "_");
    const path = `${userId}/${reportId}/${crypto.randomUUID()}-${safeName}`;
    const { error } = await supabase.storage.from("report-media").upload(path, file, { contentType: file.type, upsert: false });
    if (error) throw error;
    return path;
}

export async function registerPushToken(fcmToken, platform) {
    const { data, error } = await supabase.rpc("register_device", { p_fcm_token: fcmToken, p_platform: platform });
    if (error) throw error;
    return data;
}

export const SEVERITY_COLORS = { CRITICAL: "#e11d48", HIGH: "#ea580c", MEDIUM: "#d97706", LOW: "#059669", UNKNOWN: "#6b7280" };
export const severityClass = (s) => ({ CRITICAL: "sev-critical", HIGH: "sev-high", MEDIUM: "sev-medium", LOW: "sev-low" }[s] || "sev-unknown");
export const roleFromStorage = () => localStorage.getItem("ner_role") || "AUTHORITY";
export const setRole = (r) => localStorage.setItem("ner_role", r);

const QKEY = "ner_offline_reports";
export const enqueueOffline = (r) => {
    const list = JSON.parse(localStorage.getItem(QKEY) || "[]");
    list.push({ ...r, client_uuid: r.client_uuid || crypto.randomUUID(), queued_at: new Date().toISOString() });
    localStorage.setItem(QKEY, JSON.stringify(list));
};
export const getOfflineQueue = () => JSON.parse(localStorage.getItem(QKEY) || "[]");
export const clearOfflineItem = (id) => localStorage.setItem(QKEY, JSON.stringify(getOfflineQueue().filter((x) => x.client_uuid !== id)));
export const flushOffline = async () => {
    for (const r of getOfflineQueue()) { try { await api.post("/reports", r); clearOfflineItem(r.client_uuid); } catch (e) {} }
    return getOfflineQueue().length;
};
