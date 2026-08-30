import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import MapPage from "@/pages/MapPage";
import Zones from "@/pages/Zones";
import ZoneDetail from "@/pages/ZoneDetail";
import Sensors from "@/pages/Sensors";
import Reports from "@/pages/Reports";
import Alerts from "@/pages/Alerts";
import Response from "@/pages/Response";
import Analytics from "@/pages/Analytics";
import Public from "@/pages/Public";
import FieldOfficer from "@/pages/FieldOfficer";
import Recipients from "@/pages/Recipients";
import { supabase } from "@/lib/supabaseClient";
import { registerWebPush } from "@/lib/push";

export default function App() {
    useEffect(() => {
        let active = true;
        const setup = async () => {
            const { data } = await supabase.auth.getSession();
            if (active && data.session) registerWebPush().catch(() => {});
        };
        setup();
        const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
            if (session) registerWebPush().catch(() => {});
        });
        return () => { active = false; listener.subscription.unsubscribe(); };
    }, []);

    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Navigate to="/login" replace />} />
                <Route path="/login" element={<Login />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/map" element={<MapPage />} />
                <Route path="/zones" element={<Zones />} />
                <Route path="/zones/:id" element={<ZoneDetail />} />
                <Route path="/sensors" element={<Sensors />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/response" element={<Response />} />
                <Route path="/analytics" element={<Analytics />} />
                <Route path="/recipients" element={<Recipients />} />
                <Route path="/public" element={<Public />} />
                <Route path="/field" element={<FieldOfficer />} />
                <Route path="*" element={<Navigate to="/login" replace />} />
            </Routes>
        </BrowserRouter>
    );
}
