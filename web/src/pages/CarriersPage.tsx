import { useEffect, useState } from 'react';
import { api, type InsuranceCarrier, type Adjuster, type InsurerPayment, type CarrierMarketRateExhibit } from '../api';

// Handoff §2.8: "Jed has years of data on what carriers actually paid at
// market rate. When an adjuster offers $35-40/day, the exhibit is: this
// same carrier paid market rate on N prior claims." This page is that
// exhibit, plus the carrier/adjuster admin DemandsPage's dropdowns already
// read from but never had a create form for.
export default function CarriersPage() {
  const [carriers, setCarriers] = useState<InsuranceCarrier[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedCarrierId, setSelectedCarrierId] = useState<number | null>(null);
  const [adjusters, setAdjusters] = useState<Adjuster[]>([]);
  const [payments, setPayments] = useState<InsurerPayment[] | null>(null);
  const [exhibit, setExhibit] = useState<CarrierMarketRateExhibit | null>(null);

  const [newCarrierName, setNewCarrierName] = useState('');
  const [newCarrierFax, setNewCarrierFax] = useState('');
  const [newCarrierPhone, setNewCarrierPhone] = useState('');
  const [creatingCarrier, setCreatingCarrier] = useState(false);

  const [newAdjusterName, setNewAdjusterName] = useState('');
  const [creatingAdjuster, setCreatingAdjuster] = useState(false);

  // Edit-after-create form (BACKLOG.md: "CarriersPage can create a carrier
  // but not edit an existing one's fax/email/phone/aliases after creation
  // -- only POST /insurance-carriers/{id}/aliases exists as a partial-update
  // route today"). Closed this cycle with PATCH /insurance-carriers/{id}
  // (app/api.py) for the contact fields + this form's separate alias input
  // wired to the existing add-alias route. Deliberately does not edit
  // `name` -- that's the canonical unique key, a rename is a bigger
  // operation than this form covers.
  const [editFax, setEditFax] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editClaimsAddress, setEditClaimsAddress] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [newAlias, setNewAlias] = useState('');
  const [addingAlias, setAddingAlias] = useState(false);

  const selectedCarrier = carriers.find((c) => c.id === selectedCarrierId) ?? null;

  // Reset the edit form's fields to the freshly-selected carrier's current
  // values whenever the selection changes, so the form never shows a
  // different carrier's stale edits.
  useEffect(() => {
    setEditFax(selectedCarrier?.fax ?? '');
    setEditEmail(selectedCarrier?.email ?? '');
    setEditPhone(selectedCarrier?.phone ?? '');
    setEditClaimsAddress(selectedCarrier?.claims_mailing_address ?? '');
    setEditNotes(selectedCarrier?.notes ?? '');
  }, [selectedCarrierId]);

  // Handoff §2.8's own two named filters for the exhibit + resolved-
  // claims history. CLOSED 2026-09-05 (cron cycle) -- these were
  // previously accepted by neither the backend query params nor this
  // page's own fetch calls (BACKLOG.md small-item). Empty string means
  // "unfiltered" for all three, matching buildFilterQuery's own
  // falsy-key-omitted behavior in api.ts.
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [filterVehicleClass, setFilterVehicleClass] = useState('');

  const loadCarriers = () => {
    api.listInsuranceCarriers().then(setCarriers).catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(() => { loadCarriers(); }, []);

  useEffect(() => {
    if (selectedCarrierId == null) { setAdjusters([]); setPayments(null); setExhibit(null); return; }
    api.listAdjustersForCarrier(selectedCarrierId).then(setAdjusters).catch(() => setAdjusters([]));
    const filters = {
      date_from: filterDateFrom || undefined,
      date_to: filterDateTo || undefined,
      vehicle_class: filterVehicleClass || undefined,
    };
    api.getCarrierInsurerPayments(selectedCarrierId, filters).then(setPayments).catch(() => setPayments([]));
    api.getCarrierMarketRateExhibit(selectedCarrierId, filters).then(setExhibit).catch(() => setExhibit(null));
  }, [selectedCarrierId, filterDateFrom, filterDateTo, filterVehicleClass]);

  const handleCreateCarrier = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCarrierName.trim()) return;
    setCreatingCarrier(true);
    setError(null);
    try {
      const created = await api.createInsuranceCarrier({
        name: newCarrierName.trim(),
        fax: newCarrierFax.trim() || undefined,
        phone: newCarrierPhone.trim() || undefined,
        actor: 'dashboard',
      });
      setNewCarrierName('');
      setNewCarrierFax('');
      setNewCarrierPhone('');
      loadCarriers();
      setSelectedCarrierId(created.id);
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreatingCarrier(false);
    }
  };

  const handleCreateAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCarrierId || !newAdjusterName.trim()) return;
    setCreatingAdjuster(true);
    setError(null);
    try {
      await api.createAdjuster(selectedCarrierId, { name: newAdjusterName.trim(), actor: 'dashboard' });
      setNewAdjusterName('');
      api.listAdjustersForCarrier(selectedCarrierId).then(setAdjusters);
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreatingAdjuster(false);
    }
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCarrierId) return;
    setSavingEdit(true);
    setError(null);
    try {
      await api.updateInsuranceCarrier(selectedCarrierId, {
        fax: editFax.trim() || undefined,
        email: editEmail.trim() || undefined,
        phone: editPhone.trim() || undefined,
        claims_mailing_address: editClaimsAddress.trim() || undefined,
        notes: editNotes.trim() || undefined,
        actor: 'dashboard',
      });
      loadCarriers();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleAddAlias = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCarrierId || !newAlias.trim()) return;
    setAddingAlias(true);
    setError(null);
    try {
      await api.addInsuranceCarrierAlias(selectedCarrierId, { alias: newAlias.trim(), actor: 'dashboard' });
      setNewAlias('');
      loadCarriers();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setAddingAlias(false);
    }
  };

  return (
    <div>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}

      <div className="ek-section">
        <h2>Insurance Carriers</h2>
        <table className="ek-table">
          <thead><tr><th>Name</th><th>Fax</th><th>Phone</th><th /></tr></thead>
          <tbody>
            {carriers.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.fax ?? '—'}</td>
                <td>{c.phone ?? '—'}</td>
                <td>
                  <button className="ek-btn secondary" onClick={() => setSelectedCarrierId(c.id)}>
                    {selectedCarrierId === c.id ? 'Selected' : 'View exhibit'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <form onSubmit={handleCreateCarrier} className="ek-field-row" style={{ marginTop: 12 }}>
          <label>New carrier</label>
          <input className="ek-input" value={newCarrierName} onChange={(e) => setNewCarrierName(e.target.value)} placeholder="Name" />
          <input className="ek-input" value={newCarrierFax} onChange={(e) => setNewCarrierFax(e.target.value)} placeholder="Fax" style={{ width: 130 }} />
          <input className="ek-input" value={newCarrierPhone} onChange={(e) => setNewCarrierPhone(e.target.value)} placeholder="Phone" style={{ width: 130 }} />
          <button className="ek-btn" type="submit" disabled={creatingCarrier || !newCarrierName.trim()}>
            {creatingCarrier ? 'Creating…' : 'Create carrier'}
          </button>
        </form>
      </div>

      {selectedCarrierId != null && (
        <>
          <div className="ek-section">
            <h2>Edit Carrier #{selectedCarrierId} — {selectedCarrier?.name}</h2>
            <p style={{ fontSize: 12, color: 'var(--ek-gray)', marginTop: -6, marginBottom: 14 }}>
              Corrects the carrier's own contact record in place (BACKLOG.md — carrier
              edit-after-creation). Renaming the carrier or removing an alias is not
              supported here; canonical name is the unique key and aliases only append.
            </p>
            <form onSubmit={handleSaveEdit} className="ek-field-row" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
              <label>Fax</label>
              <input className="ek-input" value={editFax} onChange={(e) => setEditFax(e.target.value)} style={{ width: 130 }} />
              <label>Email</label>
              <input className="ek-input" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} style={{ width: 180 }} />
              <label>Phone</label>
              <input className="ek-input" value={editPhone} onChange={(e) => setEditPhone(e.target.value)} style={{ width: 130 }} />
              <label>Claims mailing address</label>
              <input className="ek-input" value={editClaimsAddress} onChange={(e) => setEditClaimsAddress(e.target.value)} style={{ width: 220 }} />
              <label>Notes</label>
              <input className="ek-input" value={editNotes} onChange={(e) => setEditNotes(e.target.value)} style={{ width: 180 }} />
              <button className="ek-btn" type="submit" disabled={savingEdit}>
                {savingEdit ? 'Saving…' : 'Save changes'}
              </button>
            </form>
            <div className="ek-field-row" style={{ marginBottom: 4 }}>
              <label>Aliases</label>
              <span style={{ fontSize: 13 }}>{selectedCarrier?.aliases.length ? selectedCarrier.aliases.join(', ') : '—'}</span>
            </div>
            <form onSubmit={handleAddAlias} className="ek-field-row">
              <input className="ek-input" value={newAlias} onChange={(e) => setNewAlias(e.target.value)} placeholder="Add alias (e.g. a variant spelling)" style={{ width: 220 }} />
              <button className="ek-btn secondary" type="submit" disabled={addingAlias || !newAlias.trim()}>
                {addingAlias ? 'Adding…' : 'Add alias'}
              </button>
            </form>
          </div>

          <div className="ek-section">
            <h2>Market-Rate Exhibit — Carrier #{selectedCarrierId}</h2>
            <p style={{ fontSize: 12, color: 'var(--ek-gray)', marginTop: -6, marginBottom: 14 }}>
              "This same carrier paid market rate on N prior claims" — the exhibit for a lowball offer.
            </p>
            <div className="ek-field-row" style={{ marginBottom: 14 }}>
              <label>From</label>
              <input
                className="ek-input" type="date" style={{ width: 150 }}
                value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)}
              />
              <label>To</label>
              <input
                className="ek-input" type="date" style={{ width: 150 }}
                value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)}
              />
              <label>Vehicle class</label>
              <select
                className="ek-input" style={{ width: 130 }}
                value={filterVehicleClass} onChange={(e) => setFilterVehicleClass(e.target.value)}
              >
                <option value="">All</option>
                <option value="ev">EV</option>
                <option value="gas">Gas</option>
                <option value="suv">SUV</option>
                <option value="truck">Truck</option>
                <option value="sedan">Sedan</option>
                <option value="van">Van</option>
                <option value="other">Other</option>
              </select>
              {(filterDateFrom || filterDateTo || filterVehicleClass) && (
                <button
                  className="ek-btn secondary"
                  onClick={() => { setFilterDateFrom(''); setFilterDateTo(''); setFilterVehicleClass(''); }}
                >
                  Clear filters
                </button>
              )}
            </div>
            {exhibit === null ? <p>Loading…</p> : (
              <table className="ek-table">
                <thead><tr><th>Claim Count</th><th>Avg Demanded</th><th>Avg Paid</th><th>Avg Market Rate</th></tr></thead>
                <tbody>
                  <tr>
                    <td>{exhibit.claim_count}</td>
                    <td>{exhibit.avg_amount_demanded ? `$${exhibit.avg_amount_demanded}` : '—'}</td>
                    <td>{exhibit.avg_amount_paid ? `$${exhibit.avg_amount_paid}` : '—'}</td>
                    <td>{exhibit.avg_market_rate ? `$${exhibit.avg_market_rate}` : '—'}</td>
                  </tr>
                </tbody>
              </table>
            )}
          </div>

          <div className="ek-section">
            <h2>Resolved Claims History</h2>
            {payments === null ? <p>Loading…</p> : payments.length === 0 ? (
              <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>No resolved demands against this carrier yet.</p>
            ) : (
              <table className="ek-table">
                <thead><tr><th>Demand</th><th>Rental</th><th>Vehicle Class</th><th>Demanded</th><th>Paid</th><th>Days to Resolve</th><th>Resolved</th></tr></thead>
                <tbody>
                  {payments.map((p) => (
                    <tr key={p.id}>
                      <td>#{p.demand_id}</td>
                      <td>#{p.rental_id}</td>
                      <td>{p.vehicle_class ?? '—'}</td>
                      <td>${p.amount_demanded}</td>
                      <td>${p.amount_paid}</td>
                      <td>{p.days_to_resolve ?? '—'}</td>
                      <td>{new Date(p.resolved_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="ek-section">
            <h2>Adjusters at Carrier #{selectedCarrierId}</h2>
            <table className="ek-table">
              <thead><tr><th>Name</th><th>Phone</th><th>Email</th></tr></thead>
              <tbody>
                {adjusters.map((a) => (
                  <tr key={a.id}><td>{a.name}</td><td>{a.phone ?? '—'}</td><td>{a.email ?? '—'}</td></tr>
                ))}
              </tbody>
            </table>
            <form onSubmit={handleCreateAdjuster} className="ek-field-row" style={{ marginTop: 12 }}>
              <label>New adjuster</label>
              <input className="ek-input" value={newAdjusterName} onChange={(e) => setNewAdjusterName(e.target.value)} placeholder="Name" />
              <button className="ek-btn" type="submit" disabled={creatingAdjuster || !newAdjusterName.trim()}>
                {creatingAdjuster ? 'Creating…' : 'Add adjuster'}
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
