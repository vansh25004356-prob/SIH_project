import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Shell from "@/components/Shell";
import { api, severityClass } from "@/lib/api";

export default function Response() {
    const nav = useNavigate();
    const [items, setItems] = useState([]);
    useEffect(() => { api.get("/response/priorities").then(r => setItems(r.data)); }, []);
    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="response-page">
                <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Response prioritization</div>
                    <h1 className="font-heading text-3xl tracking-tighter font-bold">Where to respond first</h1>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                    {["P1", "P2", "P3", "P4"].map(pkey => (
                        <div key={pkey} className="tactical-card p-3" data-testid={`col-${pkey}`}>
                            <div className={`chip ${pkey === "P1" ? "sev-critical pulse-critical" : pkey === "P2" ? "sev-high" : pkey === "P3" ? "sev-medium" : "sev-low"}`}>{pkey}</div>
                            <div className="space-y-2 mt-3">
                                {items.filter(i => i.priority === pkey).map(i => (
                                    <div key={i.zone_id} onClick={() => nav(`/zones/${i.zone_id}`)} className="border border-[var(--border)] p-2 hover:bg-white/[0.03] cursor-pointer">
                                        <div className="font-heading text-sm">{i.zone_name}</div>
                                        <div className="font-mono text-[10px] text-[var(--text-2)]">{i.district}, {i.state}</div>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className={`chip ${severityClass(i.severity)}`}>{i.severity}</span>
                                            <span className="font-mono text-[10px]">score {i.score}</span>
                                        </div>
                                        {i.unknown_factors?.length ? <div className="font-mono text-[10px] text-[var(--sev-medium)] mt-1">Missing: {i.unknown_factors.join(", ")}</div> : null}
                                    </div>
                                ))}
                                {!items.filter(i => i.priority === pkey).length && <div className="font-mono text-[10px] text-[var(--text-2)]">— none —</div>}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </Shell>
    );
}
