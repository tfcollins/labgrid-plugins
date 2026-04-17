import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Places from "./pages/Places";
import Resources from "./pages/Resources";
import Reservations from "./pages/Reservations";
import Statistics from "./pages/Statistics";
import EventLog from "./pages/EventLog";
import ExporterDetail from "./pages/ExporterDetail";
import Topology from "./pages/Topology";
import Help from "./pages/Help";
import PlaceDetail from "./pages/PlaceDetail";
import PlaceWizard from "./pages/PlaceWizard";
import Console from "./pages/Console";
import Recordings from "./pages/Recordings";
import RecordingPlayer from "./pages/RecordingPlayer";
import Login from "./pages/Login";
import AdminUsers from "./pages/AdminUsers";
import RequireAuth from "./auth/RequireAuth";
import RequireAdmin from "./auth/RequireAdmin";

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin/users" element={<RequireAdmin><AdminUsers /></RequireAdmin>} />
        <Route path="/" element={<Dashboard />} />
        <Route path="/places" element={<Places />} />
        <Route path="/resources" element={<Resources />} />
        <Route
          path="/reservations"
          element={<RequireAuth><Reservations /></RequireAuth>}
        />
        <Route path="/statistics" element={<Statistics />} />
        <Route path="/events" element={<EventLog />} />
        <Route path="/exporters/:exporterName" element={<ExporterDetail />} />
        <Route path="/topology" element={<Topology />} />
        <Route path="/help" element={<Help />} />
        <Route path="/places/new" element={<RequireAuth><PlaceWizard /></RequireAuth>} />
        <Route path="/places/:name" element={<RequireAuth><PlaceDetail /></RequireAuth>} />
        <Route path="/places/:name/console/:resource" element={<RequireAuth><Console /></RequireAuth>} />
        <Route path="/recordings" element={<RequireAuth><Recordings /></RequireAuth>} />
        <Route path="/recordings/:id" element={<RequireAuth><RecordingPlayer /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default App;
