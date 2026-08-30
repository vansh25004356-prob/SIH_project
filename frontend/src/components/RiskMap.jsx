import { useEffect, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { SEVERITY_COLORS } from "@/lib/api";
import { api } from "@/lib/api";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({ iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png", iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png", shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png" });

function FlyTo({ target }) { const map=useMap(); useEffect(()=>{if(target) map.flyTo([target.lat,target.lon],target.zoom||10,{duration:1.2});},[target,map]); return null; }

export default function RiskMap({ onSelectZone, focusTarget, reports=[], height="100%", showLegend=true, publicMode=false, layers={zones:true,sensors:true,roads:true,villages:true,reports:true} }) {
    const [zonesFC,setZones]=useState(null),[sensorsFC,setSensors]=useState(null),[roadsFC,setRoads]=useState(null),[villagesFC,setVillages]=useState(null),[heatPts,setHeatPts]=useState([]);
    const load=async()=>{
        const prefix=publicMode?"/public/gis":"/gis";
        const requests=[api.get(`${prefix}/risk-zones`), api.get(`${prefix}/roads`), api.get(`${prefix}/villages`), api.get(`${prefix}/heatmap`)];
        if(!publicMode) requests.splice(1,0,api.get("/gis/sensors"));
        const results=await Promise.all(requests);
        if(publicMode){setZones(results[0].data);setRoads(results[1].data);setVillages(results[2].data);setHeatPts(results[3].data);}
        else {setZones(results[0].data);setSensors(results[1].data);setRoads(results[2].data);setVillages(results[3].data);setHeatPts(results[4].data);}
    };
    useEffect(()=>{load().catch(()=>{});},[publicMode]);
    const styleZone=(f)=>{const sev=f.properties.severity||"UNKNOWN";const color=SEVERITY_COLORS[sev]||"#6b7280";return {color,weight:1.2,fillColor:color,fillOpacity:sev==="UNKNOWN"?0.05:0.22};};
    return <div className="relative w-full" style={{height}} data-testid="risk-map">
        <MapContainer center={[26.2,92.5]} zoom={7} scrollWheelZoom style={{height:"100%",width:"100%"}}>
            <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {layers.zones&&zonesFC&&<GeoJSON data={zonesFC} style={styleZone} onEachFeature={(f,layer)=>{const p=f.properties;layer.bindTooltip(`${p.name} • ${p.severity||"UNKNOWN"}`);layer.on("click",()=>onSelectZone&&onSelectZone(p.zone_id));}}/>}
            {layers.zones&&heatPts.map(h=>{if(!h.intensity)return null;const r=6+h.intensity*22,color=SEVERITY_COLORS[h.severity]||"#6b7280";return <CircleMarker key={`heat-${h.zone_id}`} center={[h.lat,h.lon]} radius={r} pathOptions={{color,fillColor:color,fillOpacity:.28,weight:.5}}/>;})}
            {layers.roads&&roadsFC&&<GeoJSON data={roadsFC} style={f=>({color:f.properties.status==="BLOCKED"?"#e11d48":f.properties.status==="AT_RISK"?"#d97706":"#60a5fa",weight:3,dashArray:f.properties.status==="BLOCKED"?"6 4":null})} onEachFeature={(f,layer)=>layer.bindTooltip(`${f.properties.name} • ${f.properties.status}`)}/>} 
            {layers.sensors&&!publicMode&&sensorsFC&&sensorsFC.features.map((f,i)=>{const c=f.geometry.coordinates,online=f.properties.status==="ONLINE";return <CircleMarker key={`sen-${i}`} center={[c[1],c[0]]} radius={4} pathOptions={{color:online?"#10b981":"#6b7280",fillColor:online?"#10b981":"#6b7280",fillOpacity:.9}}><Popup><div className="font-mono text-xs"><div className="font-bold">{f.properties.sensor_id}</div><div>{f.properties.type}</div><div>Status: {f.properties.status}</div></div></Popup></CircleMarker>;})}
            {layers.villages&&villagesFC&&villagesFC.features.map((f,i)=>{const c=f.geometry.coordinates;return <CircleMarker key={`vil-${i}`} center={[c[1],c[0]]} radius={3} pathOptions={{color:"#f4f4f5",fillColor:"#f4f4f5",fillOpacity:.7,weight:0}}><Popup><div className="font-mono text-xs"><div className="font-bold">{f.properties.name}</div><div>{f.properties.state}</div><div>Pop: {f.properties.population}</div></div></Popup></CircleMarker>;})}
            {layers.reports&&reports.map(r=><CircleMarker key={`rep-${r.id}`} center={[r.lat,r.lon]} radius={6} pathOptions={{color:"#eab308",fillColor:"#eab308",fillOpacity:.75,weight:1}}><Popup><div className="font-mono text-xs"><div className="font-bold">{r.report_type}</div><div>{r.description}</div><div>By: {r.reporter_role}</div></div></Popup></CircleMarker>)}
            <FlyTo target={focusTarget}/>
        </MapContainer>
        {showLegend&&<div className="map-overlay left-3 bottom-8" data-testid="map-legend"><div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--text-2)] mb-1">Risk Legend</div><div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">{[["CRITICAL",SEVERITY_COLORS.CRITICAL],["HIGH",SEVERITY_COLORS.HIGH],["MEDIUM",SEVERITY_COLORS.MEDIUM],["LOW",SEVERITY_COLORS.LOW]].map(([l,c])=><div key={l} className="flex items-center gap-1.5"><span style={{background:c}} className="inline-block w-3 h-3"/><span>{l}</span></div>)}</div></div>}
    </div>;
}
