import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import LoginPage from './pages/LoginPage';
import FleetListPage from './pages/FleetListPage';
import VehicleDetailPage from './pages/VehicleDetailPage';
import RentalListPage from './pages/RentalListPage';
import RentalDetailPage from './pages/RentalDetailPage';
import DemandsPage from './pages/DemandsPage';
import TollsPage from './pages/TollsPage';
import PaymentsPage from './pages/PaymentsPage';
import CompliancePage from './pages/CompliancePage';
import PersonMatchQueuePage from './pages/PersonMatchQueuePage';
import ProposalsQueuePage from './pages/ProposalsQueuePage';
import StaffAdminPage from './pages/StaffAdminPage';

const NAV_ITEMS = [
  { to: '/', label: 'Fleet' },
  { to: '/rentals', label: 'Rentals' },
  { to: '/demands', label: 'Demands' },
  { to: '/tolls', label: 'Tolls' },
  { to: '/payments', label: 'Payments' },
  { to: '/compliance', label: 'Compliance' },
  { to: '/person-match-queue', label: 'Identity Queue' },
  { to: '/proposals', label: 'Bot Proposals' },
];

const OWNER_NAV_ITEM = { to: '/staff', label: 'Staff' };

function AppShell() {
  const { token, staff, loading, logout } = useAuth();
  const location = useLocation();

  if (!token) return <LoginPage />;
  if (loading) return <div className="ek-login"><p style={{ color: '#fff' }}>Signing in…</p></div>;
  if (!staff) return <LoginPage />;

  const navItems = staff.role === 'owner' ? [...NAV_ITEMS, OWNER_NAV_ITEM] : NAV_ITEMS;
  const activeLabel = navItems.find((n) => location.pathname === n.to || (n.to !== '/' && location.pathname.startsWith(n.to)))?.label ?? 'Elektrica';

  return (
    <div className="ek-app">
      <aside className="ek-sidebar">
        <div className="ek-brand-logo">
          Elektrica Rentals
          <small>Staff Dashboard</small>
        </div>
        <nav className="ek-nav">
          {navItems.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={location.pathname === item.to ? 'active' : ''}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="ek-main">
        <div className="ek-topbar">
          <h1>{activeLabel}</h1>
          <div>
            <span className="ek-user-chip">{staff.google_email} · {staff.role}</span>
            <button className="ek-signout" onClick={logout}>Sign out</button>
          </div>
        </div>
        <Routes>
          <Route path="/" element={<FleetListPage />} />
          <Route path="/vehicles/:id" element={<VehicleDetailPage />} />
          <Route path="/rentals" element={<RentalListPage />} />
          <Route path="/rentals/:id" element={<RentalDetailPage />} />
          <Route path="/demands" element={<DemandsPage />} />
          <Route path="/tolls" element={<TollsPage />} />
          <Route path="/payments" element={<PaymentsPage />} />
          <Route path="/compliance" element={<CompliancePage />} />
          <Route path="/person-match-queue" element={<PersonMatchQueuePage />} />
          <Route path="/proposals" element={<ProposalsQueuePage />} />
          <Route path="/staff" element={<StaffAdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </BrowserRouter>
  );
}
