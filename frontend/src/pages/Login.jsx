import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { setRole } from "@/lib/api";
import { ShieldCheck, PersonSimpleWalk, UserCircle, Wrench as WrenchIcon } from "@phosphor-icons/react";

const ROLES = [
    { id: "AUTHORITY", label: "Authority", desc: "District & disaster management authorities. Full GIS + alerts + response.", icon: ShieldCheck, dest: "/dashboard" },
    { id: "FIELD_OFFICER", label: "Field Officer", desc: "Nearby zones, sensor check-ins, on-ground reporting with GPS + photo. Offline-first.", icon: PersonSimpleWalk, dest: "/field" },
    { id: "CITIZEN", label: "Citizen", desc: "Public risk map, community alerts, submit a report.", icon: UserCircle, dest: "/public" },
    { id: "ADMIN", label: "Admin", desc: "System operator. Model info, seeding, feedback ledger.", icon: WrenchIcon, dest: "/dashboard" },
];

export default function Login() {
    const nav = useNavigate();
    const [selected, setSelected] = useState("AUTHORITY");
    const enter = () => {
        const r = ROLES.find((x) => x.id === selected);
        setRole(selected);
        nav(r.dest);
    };
    return (
        <div className="min-h-screen topo-bg flex items-center justify-center px-4" data-testid="login-page">
            <div className="max-w-4xl w-full">
                <div className="flex items-center gap-3 mb-8">
                    <div className="w-10 h-10 flex items-center justify-center bg-[var(--sev-critical)] text-white font-heading font-bold">NS</div>
                    <div>
                        <div className="font-heading text-3xl md:text-4xl tracking-tighter font-bold">NER-SLIDE</div>
                        <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--text-2)]">AI Landslide Early Warning · North East India</div>
                    </div>
                </div>
                <div className="tactical-card p-6 md:p-8">
                    <div className="font-mono uppercase tracking-[0.15em] text-xs text-[var(--text-2)] mb-4">Select operational role</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {ROLES.map(({ id, label, desc, icon: Icon }) => (
                            <button
                                key={id}
                                data-testid={`role-${id.toLowerCase()}`}
                                onClick={() => setSelected(id)}
                                className={`text-left p-4 border transition-colors ${selected === id ? "border-[var(--sev-critical)] bg-white/[0.04]" : "border-[var(--border)] hover:bg-white/[0.03]"}`}
                            >
                                <div className="flex items-start gap-3">
                                    <Icon size={22} weight="regular" />
                                    <div>
                                        <div className="font-heading font-semibold">{label}</div>
                                        <div className="text-sm text-[var(--text-2)] leading-relaxed">{desc}</div>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                    <div className="flex items-center justify-between mt-6 pt-4 border-t border-[var(--border)]">
                        <div className="font-mono text-[11px] text-[var(--text-2)] uppercase tracking-[0.15em]">
                            V5 model · 13 features · loaded once per process
                        </div>
                        <button
                            onClick={enter}
                            data-testid="enter-btn"
                            className="px-5 py-2 bg-[var(--sev-critical)] text-white font-mono uppercase tracking-[0.15em] text-xs hover:bg-red-500 transition-colors"
                        >
                            Enter Ops Console
                        </button>
                    </div>
                </div>
                <div className="mt-4 font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)]">
                    Demo data is clearly labelled DEMO. Sources: Open-Meteo · OSM · DEM.
                </div>
            </div>
        </div>
    );
}
