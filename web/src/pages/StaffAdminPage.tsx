// StaffAdminPage.tsx — mirrors VLS's StaffAdminPage.tsx pattern
// (same repo family), adapted to Elektrica's actual API shape:
//   - Roles are owner/staff (not attorney/paralegal/admin).
//   - POST /staff requires an ALREADY-RESOLVED person_id (Elektrica's
//     staff-provisioning route deliberately does not create a new
//     platform.person -- see app/api.py's StaffProvisionRequest
//     docstring). There is no "list all staff" route in this API
//     (only GET /staff/{google_email} by exact email and POST to
//     create/POST .../active to toggle) -- this page works with what
//     exists: a lookup-by-email form plus provision/toggle actions,
//     rather than a table of every staff member (that would need a
//     new backend route this build didn't add; flagged in the summary).
import { useState } from 'react';
import { api, type StaffUser, type StaffRole } from '../api';
import { useAuth } from '../auth';

const ROLE_OPTIONS: StaffRole[] = ['owner', 'staff'];

export default function StaffAdminPage() {
  const { staff } = useAuth();
  const [lookupEmail, setLookupEmail] = useState('');
  const [found, setFound] = useState<StaffUser | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [newPersonId, setNewPersonId] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState<StaffRole>('staff');

  if (staff?.role !== 'owner') {
    return <p style={{ color: 'var(--ek-danger)' }}>Owner access required.</p>;
  }

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!lookupEmail.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const row = await api.getStaff(lookupEmail.trim());
      setFound(row);
    } catch (e: any) {
      if (e.status === 404) setFound(null);
      else setError(e.body?.detail ?? e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleProvision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPersonId.trim() || !newEmail.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const row = await api.provisionStaff({
        person_id: Number(newPersonId.trim()),
        role: newRole,
        google_email: newEmail.trim(),
        actor: staff.google_email,
      });
      setFound(row);
      setLookupEmail(row.google_email);
      setNewPersonId(''); setNewEmail('');
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleToggleActive = async () => {
    if (!found) return;
    if (found.active) {
      const ok = window.confirm(`Deactivate ${found.google_email}? They will lose all dashboard access immediately (re-checked on their very next request, not just at token expiry).`);
      if (!ok) return;
    }
    setBusy(true);
    setError(null);
    try {
      const row = await api.setStaffActive(found.google_email, !found.active, staff.google_email);
      setFound(row);
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p style={{ fontSize: 13, color: 'var(--ek-gray)', marginBottom: 20 }}>
        This API has no "list all staff" route yet — look up a staff member by their exact Google email below,
        or provision a new one against an already-resolved platform.person id (identity resolution happens
        upstream via the person-match-queue / renter intake flow, not here).
      </p>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}

      <div className="ek-section">
        <h2>Look Up Staff</h2>
        <form onSubmit={handleLookup} className="ek-field-row">
          <input
            type="email"
            className="ek-input"
            placeholder="name@elektricarentals.com"
            value={lookupEmail}
            onChange={(e) => setLookupEmail(e.target.value)}
            style={{ flex: 1, minWidth: 240 }}
          />
          <button type="submit" className="ek-btn" disabled={busy || !lookupEmail.trim()}>
            {busy ? 'Looking…' : 'Look up'}
          </button>
        </form>
      </div>

      {found === null && (
        <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>No staff_user found for that email.</p>
      )}

      {found && (
        <div className="ek-section">
          <h2>{found.google_email}</h2>
          <dl style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 10 }}>
            <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Person ID</dt>
            <dd style={{ margin: 0 }}>{found.person_id}</dd>
            <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Role</dt>
            <dd style={{ margin: 0, textTransform: 'capitalize' }}>{found.role}</dd>
            <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Status</dt>
            <dd style={{ margin: 0 }}><span className={`ek-badge ${found.active ? 'ok' : 'danger'}`}>{found.active ? 'Active' : 'Inactive'}</span></dd>
          </dl>
          <button
            className="ek-btn secondary"
            style={{ marginTop: 12 }}
            onClick={handleToggleActive}
            disabled={busy || found.google_email === staff.google_email}
            title={found.google_email === staff.google_email ? "Can't deactivate your own account" : undefined}
          >
            {found.active ? 'Deactivate' : 'Reactivate'}
          </button>
        </div>
      )}

      <div className="ek-section">
        <h2>Provision New Staff</h2>
        <form onSubmit={handleProvision} className="ek-field-row">
          <label>Person ID</label>
          <input className="ek-input" value={newPersonId} onChange={(e) => setNewPersonId(e.target.value)} style={{ width: 100 }} />
          <label>Email</label>
          <input type="email" className="ek-input" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} style={{ minWidth: 220 }} />
          <label>Role</label>
          <select className="ek-select" value={newRole} onChange={(e) => setNewRole(e.target.value as StaffRole)}>
            {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <button type="submit" className="ek-btn" disabled={busy || !newPersonId.trim() || !newEmail.trim()}>
            {busy ? 'Provisioning…' : 'Provision'}
          </button>
        </form>
        <p style={{ fontSize: 12, color: 'var(--ek-gray)', marginTop: 8 }}>
          Note: this route requires a privileged (non-elektrica_app) DB connection per the backend's own documented
          role gap (migration 011 — elektrica_app has SELECT-only on staff_user). It will surface a clear 403 rather
          than silently failing if the backend is running under the restricted role.
        </p>
      </div>
    </div>
  );
}
