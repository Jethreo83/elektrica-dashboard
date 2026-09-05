// src/api.ts — thin typed fetch wrapper. Same conventions as VLS's
// api.ts: Bearer token from auth.tsx, 401 -> force logout, ApiError
// carries status+body for callers to render.
//
// IMPORTANT (same real bug VLS hit in CaseListPage): node-postgres /
// psycopg serialize bigint id columns as STRINGS in JSON to avoid
// silent precision loss above Number.MAX_SAFE_INTEGER. Every coerce*
// helper below runs Number() on every id-shaped field before this
// frontend does any comparison/sort/Set-lookup on it.
import { getToken } from './auth';

const API_BASE = import.meta.env.VITE_API_BASE_URL as string;
const STORAGE_KEY = 'elektrica_dashboard_token';

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any) {
    super(body?.detail ?? `API error ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem(STORAGE_KEY);
    window.location.href = '/';
    throw new ApiError(401, { detail: 'session_expired' });
  }

  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

// ---------------------------------------------------------------------------
// Types matching app/api.py's Pydantic response models.
// ---------------------------------------------------------------------------

export type VehicleStatus = 'available' | 'out' | 'maintenance' | 'retired';
export type RentalState =
  | 'active' | 'finished' | 'needs_demand' | 'needs_more_information'
  | 'demand_sent' | 'negotiating' | 'no_offer' | 'needs_lawsuit'
  | 'needs_served' | 'in_litigation' | 'resolved';
export type RentalBilledTo = 'carrier' | 'self' | 'body_shop';
export type EventSource = 'manual' | 'jotform' | 'bot_proposal' | 'ringcentral' | 'system';
export type DemandType = 'primary_insurer' | 'uim' | 'balance_to_renter';
export type DemandRecipientType = 'carrier' | 'renter';
export type DemandStatus = 'draft' | 'sent' | 'negotiating' | 'no_offer' | 'accepted' | 'resolved';
export type PaymentSource = 'authorize_net' | 'check' | 'insurer_eft' | 'manual';
export type ComplianceItemType = 'dealer_license' | 'registration' | 'insurance' | 'other';
export type ComplianceItemStatus = 'active' | 'expiring_soon' | 'expired' | 'renewed';
export type StaffRole = 'owner' | 'staff';

export interface Vehicle {
  id: number;
  vin: string;
  status: VehicleStatus;
  current_position: Record<string, unknown> | null;
}

export interface Renter {
  id: number;
  person_id: number;
  jotform_submission_ref: string | null;
  drive_folder_ref: string | null;
}

export interface Rental {
  id: number;
  vehicle_id: number;
  renter_id: number;
  body_shop: string | null;
  rental_type: string | null;
  billed_to: RentalBilledTo | null;
  current_state: RentalState;
  vls_case_id: number | null;
  assignment_document_ref: string | null;
}

export interface RentalEvent {
  id: number;
  rental_id: number;
  event_type: string;
  source: EventSource;
  confirmed: boolean;
}

export interface Demand {
  id: number;
  rental_id: number;
  demand_type: DemandType;
  recipient_type: DemandRecipientType;
  amount: string;
  status: DemandStatus;
  carrier_id: number | null;
  adjuster_id: number | null;
  sent_via: string | null;
}

export interface Toll {
  id: number;
  rental_id: number;
  tolloptics_record_id: string;
  amount: string;
  toll_date: string;
  confirmed: boolean;
}

export interface Payment {
  id: number;
  rental_id: number;
  demand_id: number | null;
  source: PaymentSource;
  amount: string;
}

export interface ComplianceItem {
  id: number;
  item_type: ComplianceItemType;
  description: string;
  expiration_date: string;
  status: ComplianceItemStatus;
  vehicle_id: number | null;
  related_document_id: number | null;
}

export interface StaffUser {
  id: number;
  person_id: number;
  role: StaffRole;
  google_email: string;
  active: boolean;
  provisioned_by_staff_user_id: number | null;
}

export interface PersonMatchQueueItem {
  id: number;
  candidate_person_id: number;
  first_name: string;
  last_name: string;
  date_of_birth: string | null;
  email_normalized: string | null;
  phone_normalized: string | null;
  match_reason: string;
  source_project: string;
  submitted_by: string;
  submitted_at: string;
}

export interface PersonMatchQueueDecisionResult {
  queue_id: number;
  decision: string;
  resulting_person_id: number;
  source_project: string;
  renter: Renter | null;
}

export type ProposalKind = 'departure' | 'return' | 'dates' | 'tolls';
export type ProposalStatus = 'pending' | 'accepted' | 'rejected';

export interface Proposal {
  id: number;
  rental_id: number;
  kind: ProposalKind;
  proposed_values: Record<string, unknown>;
  source_system: string;
  status: ProposalStatus;
}

export interface InsuranceCarrier {
  id: number;
  name: string;
  aliases: string[];
  fax: string | null;
  email: string | null;
  phone: string | null;
  claims_mailing_address: string | null;
  notes: string | null;
}

export interface Adjuster {
  id: number;
  carrier_id: number;
  name: string;
  phone: string | null;
  email: string | null;
  notes: string | null;
}

export interface InsurerPayment {
  id: number;
  demand_id: number;
  rental_id: number;
  carrier_id: number;
  adjuster_id: number | null;
  claim_ref: string | null;
  vehicle_class: string | null;
  rental_start_date: string | null;
  rental_end_date: string | null;
  market_rate_at_time: string | null;
  amount_demanded: string;
  amount_paid: string;
  days_to_resolve: number | null;
  resolved_at: string;
  source: string;
  source_ref: string | null;
  frozen: boolean;
}

export interface CarrierMarketRateExhibit {
  carrier_id: number;
  claim_count: number;
  avg_amount_demanded: string | null;
  avg_amount_paid: string | null;
  avg_market_rate: string | null;
}

// ---------------------------------------------------------------------------
// bigint-as-string coercion helpers -- run Number() on every id field
// returned from the API before this frontend touches it.
// ---------------------------------------------------------------------------

function coerceVehicle(v: any): Vehicle {
  return { ...v, id: Number(v.id) };
}
function coerceRental(r: any): Rental {
  return {
    ...r,
    id: Number(r.id),
    vehicle_id: Number(r.vehicle_id),
    renter_id: Number(r.renter_id),
    vls_case_id: r.vls_case_id === null ? null : Number(r.vls_case_id),
  };
}
function coerceRentalEvent(e: any): RentalEvent {
  return { ...e, id: Number(e.id), rental_id: Number(e.rental_id) };
}
function coerceDemand(d: any): Demand {
  return {
    ...d,
    id: Number(d.id),
    rental_id: Number(d.rental_id),
    carrier_id: d.carrier_id === null ? null : Number(d.carrier_id),
    adjuster_id: d.adjuster_id === null ? null : Number(d.adjuster_id),
  };
}
function coerceToll(t: any): Toll {
  return { ...t, id: Number(t.id), rental_id: Number(t.rental_id) };
}
function coercePayment(p: any): Payment {
  return {
    ...p,
    id: Number(p.id),
    rental_id: Number(p.rental_id),
    demand_id: p.demand_id === null ? null : Number(p.demand_id),
  };
}
function coerceComplianceItem(c: any): ComplianceItem {
  return {
    ...c,
    id: Number(c.id),
    vehicle_id: c.vehicle_id === null ? null : Number(c.vehicle_id),
    related_document_id: c.related_document_id === null ? null : Number(c.related_document_id),
  };
}
function coerceStaff(s: any): StaffUser {
  return {
    ...s,
    id: Number(s.id),
    person_id: Number(s.person_id),
    provisioned_by_staff_user_id: s.provisioned_by_staff_user_id === null ? null : Number(s.provisioned_by_staff_user_id),
  };
}
function coerceQueueItem(q: any): PersonMatchQueueItem {
  return { ...q, id: Number(q.id), candidate_person_id: Number(q.candidate_person_id) };
}
function coerceCarrier(c: any): InsuranceCarrier {
  return { ...c, id: Number(c.id) };
}

// Shared by getCarrierInsurerPayments/getCarrierMarketRateExhibit --
// builds a '?date_from=...&date_to=...&vehicle_class=...' suffix from
// only the keys actually present, or '' when none are set (so an
// unfiltered call's URL is byte-identical to before this filter
// support existed).
function buildFilterQuery(filters?: { date_from?: string; date_to?: string; vehicle_class?: string }): string {
  if (!filters) return '';
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.vehicle_class) params.set('vehicle_class', filters.vehicle_class);
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}
function coerceAdjuster(a: any): Adjuster {
  return { ...a, id: Number(a.id), carrier_id: Number(a.carrier_id) };
}
function coerceRenter(r: any): Renter {
  return { ...r, id: Number(r.id), person_id: Number(r.person_id) };
}

export interface FleetBoardOutRow {
  vehicle_id: number;
  vin: string;
  current_position: Record<string, unknown> | null;
  position_updated_at: string | null;
  rental_id: number | null;
  body_shop: string | null;
  rental_type: string | null;
  current_state: RentalState | null;
  start_date: string | null;
  end_date: string | null;
  first_name: string | null;
  last_name: string | null;
}
export interface FleetBoardAvailableRow {
  vehicle_id: number;
  vin: string;
  notes: string | null;
  // Always null today -- migration 015 dropped vehicle.class (handoff
  // §2.5 said "grouped by class" before that correction). Kept in the
  // shape so a frontend grouping UI can be added later without a
  // response-shape change. See docs/BACKLOG.md.
  class: null;
}
function coerceFleetBoardOutRow(r: any): FleetBoardOutRow {
  return { ...r, vehicle_id: Number(r.vehicle_id), rental_id: r.rental_id === null ? null : Number(r.rental_id) };
}
function coerceFleetBoardAvailableRow(r: any): FleetBoardAvailableRow {
  return { ...r, vehicle_id: Number(r.vehicle_id) };
}
function coerceProposal(p: any): Proposal {
  return { ...p, id: Number(p.id), rental_id: Number(p.rental_id) };
}

export const api = {
  // Fleet
  fleetAvailable: () => apiFetch<Vehicle[]>('/fleet/available').then((rows) => rows.map(coerceVehicle)),
  fleetOut: () => apiFetch<Vehicle[]>('/fleet/out').then((rows) => rows.map(coerceVehicle)),
  // Fleet-board joins (handoff §2.5): Out rows carry body_shop/rental_type/
  // renter name beside the vehicle; Available rows carry a `class` key
  // that is always null today (see FleetBoardAvailableRow's own comment).
  fleetBoardOut: () => apiFetch<FleetBoardOutRow[]>('/fleet-board/out').then((rows) => rows.map(coerceFleetBoardOutRow)),
  fleetBoardAvailable: () => apiFetch<FleetBoardAvailableRow[]>('/fleet-board/available').then((rows) => rows.map(coerceFleetBoardAvailableRow)),
  getVehicle: (id: number) => apiFetch<Vehicle>(`/vehicles/${id}`).then(coerceVehicle),
  getVehicleByVin: (vin: string) => apiFetch<Vehicle>(`/vehicles/vin/${encodeURIComponent(vin)}`).then(coerceVehicle),
  vehicleRevenueSummary: () => apiFetch<any[]>('/vehicles/revenue-summary'),
  createVehicle: (body: { vin: string; actor: string; status?: VehicleStatus; notes?: string }) =>
    apiFetch<Vehicle>('/vehicles', { method: 'POST', body: JSON.stringify(body) }).then(coerceVehicle),

  // Renters
  getRenter: (id: number) => apiFetch<Renter>(`/renters/${id}`).then(coerceRenter),
  getRenterByPerson: (personId: number) => apiFetch<Renter>(`/renters/by-person/${personId}`).then(coerceRenter),

  // Person match queue
  listPendingPersonMatches: () =>
    apiFetch<PersonMatchQueueItem[]>('/person-match-queue/pending').then((rows) => rows.map(coerceQueueItem)),
  decidePersonMatch: (queueId: number, body: { decision: 'confirmed_match' | 'confirmed_split'; actor: string }) =>
    apiFetch<PersonMatchQueueDecisionResult>(`/person-match-queue/${queueId}/decision`, {
      method: 'POST',
      body: JSON.stringify(body),
    }).then((r) => ({
      ...r,
      queue_id: Number(r.queue_id),
      resulting_person_id: Number(r.resulting_person_id),
      renter: r.renter ? coerceRenter(r.renter) : null,
    })),

  // Rental proposals (bot interface, handoff §1.7) -- POST is X-Api-Key
  // gated server-side (require_bot_api_key), written by the future
  // rental-operations bot, never by this dashboard. This frontend only
  // exercises the human-review half: list pending, accept/reject.
  listPendingProposals: () =>
    apiFetch<Proposal[]>('/proposals/pending').then((rows) => rows.map(coerceProposal)),
  decideProposal: (proposalId: number, body: { status: 'accepted' | 'rejected'; actor: string }) =>
    apiFetch<Proposal>(`/proposals/${proposalId}/decision`, {
      method: 'POST',
      body: JSON.stringify(body),
    }).then(coerceProposal),

  // Rentals
  listBlockedRentals: () => apiFetch<any[]>('/rentals/blocked'),
  listRentals: (currentState?: RentalState) =>
    apiFetch<any[]>(`/rentals${currentState ? `?current_state=${currentState}` : ''}`).then((rows) => rows.map(coerceRental)),
  getRental: (id: number) => apiFetch<Rental>(`/rentals/${id}`).then(coerceRental),
  getRentalEvents: (id: number) => apiFetch<RentalEvent[]>(`/rentals/${id}/events`).then((rows) => rows.map(coerceRentalEvent)),
  createRental: (body: {
    vehicle_id: number; renter_id: number; actor: string; body_shop?: string;
    rental_type?: string; billed_to?: RentalBilledTo; start_date?: string; end_date?: string;
  }) => apiFetch<Rental>('/rentals', { method: 'POST', body: JSON.stringify(body) }).then(coerceRental),
  transitionRental: (id: number, body: {
    target_state: RentalState; actor: string; source?: EventSource; source_ref?: string; notes?: string;
  }) => apiFetch<Rental>(`/rentals/${id}/transition`, { method: 'POST', body: JSON.stringify(body) }).then(coerceRental),
  linkVlsCase: (id: number, body: { vls_case_id: number; actor: string }) =>
    apiFetch<Rental>(`/rentals/${id}/vls-case`, { method: 'POST', body: JSON.stringify(body) }).then(coerceRental),

  // Demands
  getRentalDemands: (rentalId: number) =>
    apiFetch<Demand[]>(`/rentals/${rentalId}/demands`).then((rows) => rows.map(coerceDemand)),
  createDemand: (rentalId: number, body: {
    demand_type: DemandType; recipient_type: DemandRecipientType; amount: string; actor: string;
    carrier_id?: number; adjuster_id?: number; prior_demand_id?: number;
  }) => apiFetch<Demand>(`/rentals/${rentalId}/demands`, { method: 'POST', body: JSON.stringify(body) }).then(coerceDemand),
  markDemandSent: (demandId: number, body: { sent_via: string; actor: string }) =>
    apiFetch<Demand>(`/demands/${demandId}/mark-sent`, { method: 'POST', body: JSON.stringify(body) }).then(coerceDemand),
  advanceDemandStatus: (demandId: number, body: { target_status: DemandStatus; actor: string }) =>
    // POST /demands/{id}/status (app/api.py) -- covers every transition
    // past mark-sent: sent -> negotiating -> no_offer -> accepted ->
    // resolved, plus skip-ahead-to-resolved. This is the real,
    // dashboard-reachable trigger point for elektrica.insurer_payment's
    // auto-population (migration 016) -- see docs/BACKLOG.md's
    // "no HTTP route to resolve a demand" entry (resolved) for why this
    // wiring matters beyond just UI completeness.
    apiFetch<Demand>(`/demands/${demandId}/status`, { method: 'POST', body: JSON.stringify(body) }).then(coerceDemand),
  agingDemands: () => apiFetch<any[]>('/demands/aging'),

  // Tolls
  getRentalTolls: (rentalId: number) => apiFetch<Toll[]>(`/rentals/${rentalId}/tolls`).then((rows) => rows.map(coerceToll)),
  createToll: (rentalId: number, body: {
    tolloptics_record_id: string; amount: string; toll_date: string; actor: string; confirmed?: boolean;
  }) => apiFetch<Toll>(`/rentals/${rentalId}/tolls`, { method: 'POST', body: JSON.stringify(body) }).then(coerceToll),
  confirmToll: (tollId: number) => apiFetch<Toll>(`/tolls/${tollId}/confirm`, { method: 'POST' }).then(coerceToll),

  // Payments
  getRentalPayments: (rentalId: number) =>
    apiFetch<Payment[]>(`/rentals/${rentalId}/payments`).then((rows) => rows.map(coercePayment)),
  createPayment: (rentalId: number, body: {
    source: PaymentSource; amount: string; actor: string; demand_id?: number;
    external_transaction_id?: string; accounting_sync_ref?: string;
  }) => apiFetch<Payment>(`/rentals/${rentalId}/payments`, { method: 'POST', body: JSON.stringify(body) }).then(coercePayment),

  // Compliance
  complianceExpiringSoon: () => apiFetch<any[]>('/compliance/expiring-soon'),
  getComplianceItem: (id: number) => apiFetch<ComplianceItem>(`/compliance-items/${id}`).then(coerceComplianceItem),
  createComplianceItem: (body: {
    item_type: ComplianceItemType; description: string; expiration_date: string; actor: string;
    vehicle_id?: number; status?: ComplianceItemStatus;
  }) => apiFetch<ComplianceItem>('/compliance-items', { method: 'POST', body: JSON.stringify(body) }).then(coerceComplianceItem),
  updateComplianceItemStatus: (id: number, body: { status: ComplianceItemStatus; actor: string }) =>
    apiFetch<ComplianceItem>(`/compliance-items/${id}/status`, { method: 'POST', body: JSON.stringify(body) }).then(coerceComplianceItem),

  // Staff admin
  getStaff: (email: string) => apiFetch<StaffUser>(`/staff/${encodeURIComponent(email)}`).then(coerceStaff),
  provisionStaff: (body: { person_id: number; role: StaffRole; google_email: string; actor: string }) =>
    apiFetch<StaffUser>('/staff', { method: 'POST', body: JSON.stringify(body) }).then(coerceStaff),
  setStaffActive: (email: string, active: boolean, actor: string) =>
    apiFetch<StaffUser>(`/staff/${encodeURIComponent(email)}/active`, {
      method: 'POST',
      body: JSON.stringify({ active, actor }),
    }).then(coerceStaff),

  // Insurance carriers / adjusters (used by demand-creation forms)
  listInsuranceCarriers: () => apiFetch<InsuranceCarrier[]>('/insurance-carriers').then((rows) => rows.map(coerceCarrier)),
  listAdjustersForCarrier: (carrierId: number) =>
    apiFetch<Adjuster[]>(`/insurance-carriers/${carrierId}/adjusters`).then((rows) => rows.map(coerceAdjuster)),
  createInsuranceCarrier: (body: {
    name: string; aliases?: string[]; fax?: string; email?: string; phone?: string;
    claims_mailing_address?: string; notes?: string; actor: string;
  }) => apiFetch<InsuranceCarrier>('/insurance-carriers', { method: 'POST', body: JSON.stringify(body) }).then(coerceCarrier),
  createAdjuster: (carrierId: number, body: { name: string; phone?: string; email?: string; notes?: string; actor: string }) =>
    apiFetch<Adjuster>(`/insurance-carriers/${carrierId}/adjusters`, { method: 'POST', body: JSON.stringify(body) }).then(coerceAdjuster),

  // Insurer-payment tracker & market-rate exhibit (handoff §2.8) --
  // read-only from the API's own point of view: 'system' rows are
  // created exclusively by the migration-016 trigger when a
  // carrier-recipient demand resolves (see api.advanceDemandStatus
  // above), never POSTed directly by this frontend.
  //
  // date_from/date_to/vehicle_class: CLOSED 2026-09-05 (cron cycle) --
  // BACKLOG.md's small-items list flagged both routes as
  // date-range/vehicle-class filterable in the backend (handoff §2.8)
  // but client-side-only in this frontend. Both now build a real query
  // string; all three params are optional so an unfiltered call is
  // unchanged from before.
  getCarrierInsurerPayments: (
    carrierId: number,
    filters?: { date_from?: string; date_to?: string; vehicle_class?: string },
  ) => apiFetch<InsurerPayment[]>(`/insurance-carriers/${carrierId}/insurer-payments${buildFilterQuery(filters)}`),
  getCarrierMarketRateExhibit: (
    carrierId: number,
    filters?: { date_from?: string; date_to?: string; vehicle_class?: string },
  ) => apiFetch<CarrierMarketRateExhibit>(`/insurance-carriers/${carrierId}/market-rate-exhibit${buildFilterQuery(filters)}`),
};
