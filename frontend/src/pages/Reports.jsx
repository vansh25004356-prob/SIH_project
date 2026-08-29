import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";

export default function Reports() {
    const [reports, setReports] = useState([]);
    useEffect(() => { api.get("/reports?limit=200").then(r => setReports(r.data)); }, []);
    return (
        <Shell>
            <div className="p-6 space-y-4" data-testid="reports-page">
                <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-2)]">Field / Citizen Reports</div>
                    <h1 className="font-heading text-3xl tracking-tighter font-bold">On-ground reports</h1>
                </div>
                <div className="tactical-card overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="border-b border-[var(--border)] font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                            <tr>
                                <th className="text-left px-3 py-2">Time</th>
                                <th className="text-left px-3 py-2">Type</th>
                                <th className="text-left px-3 py-2">Reporter</th>
                                <th className="text-left px-3 py-2">Zone</th>
                                <th className="text-left px-3 py-2">Location</th>
                                <th className="text-left px-3 py-2">Description</th>
                            </tr>
                        </thead>
                        <tbody>
                            {reports.map(r => (
                                <tr key={r.id} className="border-b border-[var(--border)]" data-testid={`report-${r.id}`}>
                                    <td className="px-3 py-2 font-mono text-[11px] text-[var(--text-2)]">{new Date(r.timestamp).toLocaleString()}</td>
                                    <td className="px-3 py-2 font-mono text-xs">{r.report_type}</td>
                                    <td className="px-3 py-2 text-xs">{r.reporter_role} · {r.reporter_name}</td>
                                    <td className="px-3 py-2 font-mono text-xs">{r.zone_id || "—"}</td>
                                    <td className="px-3 py-2 font-mono text-[11px]">{r.lat?.toFixed(3)}, {r.lon?.toFixed(3)}</td>
                                    <td className="px-3 py-2 text-xs max-w-[24rem] truncate">{r.description}</td>
                                </tr>
                            ))}
                            {!reports.length && <tr><td colSpan={6} className="text-center py-8 font-mono text-xs text-[var(--text-2)]">No reports yet. Submit one from Citizen or Field Officer portal.</td></tr>}
                        </tbody>
                    </table>
                </div>
            </div>
        </Shell>
    );
}
