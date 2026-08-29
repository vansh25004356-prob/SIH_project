import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Popup, LayersControl, Marker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { SEVERITY_COLORS, api } from "@/lib/api";

// Fix Leaflet default marker icon in webpack
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
    shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function FlyTo({ target }) {
    const map = useMap();
    useEffect(() => {
        if (target) map.flyTo([target.lat, target.lon], target.zoom || 10, { duration: 1.2 });
    }, [target, map]);
    return null;
}

export default function RiskMap({
    onSelectZone,
    focusTarget,
    reports = [],
    height = "100%",
    showLegend = true,
    layers = { zones: true, sensors: true, roads: true, villages: true, reports: true },
}) {
    const [zonesFC, setZones] = useState(null);
    const [sensorsFC, setSensors] = useState(null);
    const [roadsFC, setRoads] = useState(null);
    const [villagesFC, setVillages] = useState(null);
    const [heatPts, setHeatPts] = useState([]);

    const load = async () => {
        const [z, s, r, v, h] = await Promise.all([
            api.get("/gis/risk-zones"),
            api.get("/gis/sensors"),
            api.get("/gis/roads"),
            api.get("/gis/villages"),
            api.get("/gis/heatmap"),
        ]);
        setZones(z.data);
        setSensors(s.data);
        setRoads(r.data);
        setVillages(v.data);
        setHeatPts(h.data);
    };
    useEffect(() => { load(); }, []);

    const styleZone = (f) => {
        const sev = f.properties.severity || "UNKNOWN";
        const color = SEVERITY_COLORS[sev] || "#6b7280";
        return { color, weight: 1.2, fillColor: color, fillOpacity: sev === "UNKNOWN" ? 0.05 : 0.22 };
    };

    return (
        <div className="relative w-full" style={{ height }} data-testid="risk-map">
            <MapContainer center={[26.2, 92.5]} zoom={7} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {layers.zones && zonesFC && (
                    <GeoJSON
                        data={zonesFC}
                        style={styleZone}
                        onEachFeature={(f, layer) => {
                            const p = f.properties;
                            layer.bindTooltip(`${p.name} • ${p.severity || "UNKNOWN"}`);
                            layer.on("click", () => onSelectZone && onSelectZone(p.zone_id));
                        }}
                    />
                )}
                {layers.zones && heatPts.map((h) => {
                    if (!h.intensity) return null;
                    const r = 6 + h.intensity * 22;
                    const color = SEVERITY_COLORS[h.severity] || "#6b7280";
                    return (
                        <CircleMarker
                            key={`heat-${h.zone_id}`}
                            center={[h.lat, h.lon]}
                            radius={r}
                            pathOptions={{ color, fillColor: color, fillOpacity: 0.28, weight: 0.5 }}
                        />
                    );
                })}
                {layers.roads && roadsFC && (
                    <GeoJSON
                        data={roadsFC}
                        style={(f) => ({
                            color: f.properties.status === "BLOCKED" ? "#e11d48"
                                : f.properties.status === "AT_RISK" ? "#d97706" : "#60a5fa",
                            weight: 3, dashArray: f.properties.status === "BLOCKED" ? "6 4" : null,
                        })}
                        onEachFeature={(f, layer) => layer.bindTooltip(`${f.properties.name} • ${f.properties.status}`)}
                    />
                )}
                {layers.sensors && sensorsFC && sensorsFC.features.map((f, i) => {
                    const c = f.geometry.coordinates;
                    const online = f.properties.status === "ONLINE";
                    return (
                        <CircleMarker
                            key={`sen-${i}`}
                            center={[c[1], c[0]]}
                            radius={4}
                            pathOptions={{ color: online ? "#10b981" : "#6b7280", fillColor: online ? "#10b981" : "#6b7280", fillOpacity: 0.9 }}
                        >
                            <Popup>
                                <div className="font-mono text-xs">
                                    <div className="font-bold">{f.properties.sensor_id}</div>
                                    <div>{f.properties.type}</div>
                                    <div>Status: {f.properties.status}</div>
                                    <div>Battery: {f.properties.battery}%</div>
                                </div>
                            </Popup>
                        </CircleMarker>
                    );
                })}
                {layers.villages && villagesFC && villagesFC.features.map((f, i) => {
                    const c = f.geometry.coordinates;
                    return (
                        <CircleMarker
                            key={`vil-${i}`}
                            center={[c[1], c[0]]}
                            radius={3}
                            pathOptions={{ color: "#f4f4f5", fillColor: "#f4f4f5", fillOpacity: 0.7, weight: 0 }}
                        >
                            <Popup>
                                <div className="font-mono text-xs">
                                    <div className="font-bold">{f.properties.name}</div>
                                    <div>{f.properties.state}</div>
                                    <div>Pop: {f.properties.population}</div>
                                </div>
                            </Popup>
                        </CircleMarker>
                    );
                })}
                {layers.reports && reports.map((r) => (
                    <CircleMarker
                        key={`rep-${r.id}`}
                        center={[r.lat, r.lon]}
                        radius={6}
                        pathOptions={{ color: "#eab308", fillColor: "#eab308", fillOpacity: 0.75, weight: 1 }}
                    >
                        <Popup>
                            <div className="font-mono text-xs">
                                <div className="font-bold">{r.report_type}</div>
                                <div>{r.description}</div>
                                <div>By: {r.reporter_role}</div>
                            </div>
                        </Popup>
                    </CircleMarker>
                ))}
                <FlyTo target={focusTarget} />
            </MapContainer>

            {showLegend && (
                <div className="map-overlay left-3 bottom-8" data-testid="map-legend">
                    <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-1">Risk Legend</div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">
                        {[
                            ["CRITICAL", SEVERITY_COLORS.CRITICAL],
                            ["HIGH", SEVERITY_COLORS.HIGH],
                            ["MEDIUM", SEVERITY_COLORS.MEDIUM],
                            ["LOW", SEVERITY_COLORS.LOW],
                        ].map(([l, c]) => (
                            <div key={l} className="flex items-center gap-1.5">
                                <span style={{ background: c }} className="inline-block w-3 h-3" />
                                <span>{l}</span>
                            </div>
                        ))}
                    </div>
                    <div className="mt-2 pt-2 border-t border-[var(--border)] font-mono text-[10px] text-[var(--text-2)]">
                        <div><span className="inline-block w-4 h-0.5 bg-[#60a5fa] align-middle mr-1" /> Road OK</div>
                        <div><span className="inline-block w-4 h-0.5 bg-[#d97706] align-middle mr-1" /> Road at risk</div>
                        <div><span className="inline-block w-4 h-0.5 bg-[#e11d48] align-middle mr-1" /> Road BLOCKED</div>
                    </div>
                </div>
            )}
        </div>
    );
}
