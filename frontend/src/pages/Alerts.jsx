import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, severityClass } from "@/lib/api";
import { Translate } from "@phosphor-icons/react";

const LANG_LABELS = { en: "English", as: "Assamese", kha: "Khasi", lus: "Mizo", ne: "Nepali", brx: "Bodo" };

export default function Alerts() {
    const [alerts, setAlerts] = useState([]);
    const [lang, setLang] = useState("en");
    useEffect(() => { api.get("/alerts").then(r => setAlerts(r.data)); }, []);
    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="alerts-page">
                <div className="flex items-center gap-3 flex-wrap">
                    <div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Broadcast</div>
                        <h1 className="font-heading text-3xl tracking-tighter font-bold">Multilingual alerts</h1>
                    </div>
                    <div className="ml-auto flex items-center gap-2 tactical-border px-3 py-1.5">
                        <Translate size={14} />
                        <select data-testid="lang-select" value={lang} onChange={e => setLang(e.target.value)} className="bg-transparent text-xs font-mono uppercase tracking-[0.15em] focus:outline-none">
                            {Object.entries(LANG_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                        </select>
                    </div>
                </div>
                <div className="space-y-2">
                    {alerts.map(a => (
                        <div key={a.id} className="tactical-card p-4" data-testid={`alert-${a.id}`}>
                            <div className="flex items-center justify-between">
                                <span className={`chip ${severityClass(a.severity)}`}>{a.severity}</span>
                                <span className="font-mono text-[10px] text-[var(--text-2)]">{new Date(a.timestamp).toLocaleString()}</span>
                            </div>
                            <p className="text-sm mt-2 leading-relaxed">{a.translations?.[lang] || a.translations?.en || a.reason}</p>
                            <div className="font-mono text-[10px] text-[var(--text-2)] mt-1">Zone {a.zone_id} · Action: {a.recommended_action}</div>
                        </div>
                    ))}
                    {!alerts.length && <div className="tactical-card p-6 text-center font-mono text-xs text-[var(--text-2)]">No alerts have been issued. Open a zone and click "Issue multilingual alert".</div>}
                </div>
            </div>
        </Shell>
    );
}
