-- 007_elektrica_jp_litigation.sql
-- Wires elektrica.rental's litigation phase to VLS's already-proven JP
-- court state machine, per Jed's decision (2026-09-04, relayed by hermes):
-- option (a) — shared/cross-schema reuse of vls.valid_next_states(), NOT
-- a fork, NOT a duplicated migration. Resolves ADR-001-elektrica-rentals-v2.md
-- section 7 item 5, previously queued in docs/OVERNIGHT_DECISIONS.md.
--
-- MECHANISM: elektrica.rental gains a nullable vls_case_id pointing at
-- vls.case. Elektrica's own litigation (handoff §1.2: "pro se, in
-- Elektrica's own name, on assigned property-damage rights") is driven
-- entirely through vls.case + vls.case_event using vls migration 002's
-- existing, already-verified valid_next_states()/trigger logic —
-- including the JP discovery trap — with ZERO new JP-specific state
-- values or transition rules defined in the elektrica schema. This is the
-- literal meaning of "import as a dependency, not fork" (handoff §1.2).
--
-- elektrica.rental's own state machine adds exactly one new state,
-- `in_litigation`, as the handoff point: needs_served -> in_litigation
-- (requires a vls.case already linked) -> resolved (gated on that
-- vls.case having reached one of vls's own terminal states — settled,
-- dismissed, or judgment — which vls.case.current_state can only reach via
-- vls's own trigger-enforced case_event sequence, already verified in
-- vls-dashboard's verify_002.sql). Elektrica never reimplements or
-- re-checks the JP sequence rules themselves — it trusts vls.case's
-- current_state as the single source of truth, exactly as intended.
--
-- vls.case_type already includes 'rental' (vls migration 002) — evidence
-- this cross-schema reuse was anticipated in the original VLS design, not
-- retrofitted.
--
-- FIELD PROVENANCE NOTE: is_first_party / cause_of_action values used when
-- creating an elektrica-owned vls.case row (see verify_007.sql) are a
-- schema-compatibility choice (false / 'other_contract' — Elektrica's
-- assigned rental-value claim against an at-fault third party reads
-- closest to a third-party contract-adjacent claim), NOT a legal
-- characterization Jed has confirmed. They only feed vls.case's
-- fee-shifting computation, which has no bearing on Elektrica's own pro se
-- suits. Flagged here rather than escalated to OVERNIGHT_DECISIONS.md —
-- it's a granular, easily-corrected field default, not an architecture or
-- external-facing decision.

-- ---------------------------------------------------------------------------
-- New state: in_litigation. Added as its own statement so it's available
-- to the function replaced below.
-- ---------------------------------------------------------------------------

ALTER TYPE elektrica.rental_state ADD VALUE 'in_litigation' AFTER 'needs_served';

-- ---------------------------------------------------------------------------
-- elektrica.rental gains the link to vls.case. Nullable: only rentals that
-- actually reach litigation get one.
-- ---------------------------------------------------------------------------

ALTER TABLE elektrica.rental ADD COLUMN vls_case_id BIGINT REFERENCES vls.case (id);
CREATE INDEX idx_rental_vls_case_id ON elektrica.rental (vls_case_id);

-- ---------------------------------------------------------------------------
-- Cross-schema grants — elektrica_app needs to read AND write vls.case /
-- vls.case_event to actually drive its own litigation through vls's
-- engine (per Jed's approval of option (a); this is what "shared reuse"
-- requires operationally, not a broader VLS-data access grant — RLS on
-- platform.person is untouched, and nothing here grants elektrica_app
-- visibility into vls.client or any VLS-client-specific data).
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA vls TO elektrica_app;
GRANT SELECT, INSERT ON vls.case TO elektrica_app;
GRANT SELECT, INSERT ON vls.case_event TO elektrica_app;
GRANT USAGE, SELECT ON vls.case_id_seq TO elektrica_app;
GRANT USAGE, SELECT ON vls.case_event_id_seq TO elektrica_app;

-- ---------------------------------------------------------------------------
-- Sequence function update: needs_served now hands off to in_litigation
-- (previously a temporary direct-to-resolved escape hatch, per migration
-- 003's own TODO). in_litigation's only next state is resolved, gated by
-- the trigger below, not by this function (this function only knows
-- elektrica's own enum — it cannot see vls.case's state, that check lives
-- in elektrica.rental_event_check_litigation_resolved below).
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elektrica.rental_valid_next_states(
  p_current_state elektrica.rental_state
) RETURNS elektrica.rental_state[] AS $$
BEGIN
  CASE p_current_state
    WHEN 'active' THEN
      RETURN ARRAY['finished']::elektrica.rental_state[];
    WHEN 'finished' THEN
      RETURN ARRAY['needs_demand']::elektrica.rental_state[];
    WHEN 'needs_demand' THEN
      RETURN ARRAY['needs_more_information', 'demand_sent']::elektrica.rental_state[];
    WHEN 'needs_more_information' THEN
      RETURN ARRAY['needs_demand', 'demand_sent']::elektrica.rental_state[];
    WHEN 'demand_sent' THEN
      RETURN ARRAY['negotiating', 'resolved']::elektrica.rental_state[];
    WHEN 'negotiating' THEN
      RETURN ARRAY['no_offer', 'resolved']::elektrica.rental_state[];
    WHEN 'no_offer' THEN
      RETURN ARRAY['needs_lawsuit', 'resolved']::elektrica.rental_state[];
    WHEN 'needs_lawsuit' THEN
      RETURN ARRAY['needs_served']::elektrica.rental_state[];
    WHEN 'needs_served' THEN
      -- JP engine handoff point (was a temporary direct-to-resolved
      -- escape hatch prior to this migration — Jed's 2026-09-04 decision
      -- closes that TODO).
      RETURN ARRAY['in_litigation']::elektrica.rental_state[];
    WHEN 'in_litigation' THEN
      -- Only path out; gated by elektrica.rental_event_check_litigation_resolved
      -- below on the linked vls.case reaching a terminal state.
      RETURN ARRAY['resolved']::elektrica.rental_state[];
    ELSE
      RETURN ARRAY[]::elektrica.rental_state[];
  END CASE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ---------------------------------------------------------------------------
-- Litigation-specific gating, layered alongside the generic sequence
-- trigger (elektrica.rental_event_enforce_sequence, migration 003) — both
-- are BEFORE INSERT triggers on elektrica.rental_event. Postgres fires
-- same-timing triggers in name order, so trg_rental_event_check_litigation
-- actually fires BEFORE trg_rental_event_enforce_sequence ('c' < 'e'
-- lexically). This does not affect correctness: both are independent
-- validity checks on the same incoming row, and either one raising first
-- still blocks the insert — order between them only changes which error
-- message surfaces first when both would fail, never whether an invalid
-- transition can slip through.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elektrica.rental_event_check_litigation()
RETURNS TRIGGER AS $$
DECLARE
  v_vls_case_id BIGINT;
  v_vls_case_state vls.case_state;
BEGIN
  IF NEW.event_type = 'in_litigation' THEN
    SELECT vls_case_id INTO v_vls_case_id FROM elektrica.rental WHERE id = NEW.rental_id;
    IF v_vls_case_id IS NULL THEN
      RAISE EXCEPTION
        'Cannot transition rental % to in_litigation: no vls.case is linked (elektrica.rental.vls_case_id is NULL). Create and link a vls.case first.',
        NEW.rental_id;
    END IF;
  END IF;

  IF NEW.event_type = 'resolved' THEN
    SELECT r.vls_case_id INTO v_vls_case_id FROM elektrica.rental r WHERE r.id = NEW.rental_id;

    -- Only enforce the vls.case terminal-state gate when the rental is
    -- currently in_litigation (i.e. this resolved transition is the
    -- litigation-exit path). resolved reached from demand_sent/negotiating/
    -- no_offer has no vls_case_id and needs no such gate — the generic
    -- sequence function already allows those paths independently.
    IF v_vls_case_id IS NOT NULL THEN
      SELECT current_state INTO v_vls_case_state FROM vls.case WHERE id = v_vls_case_id;
      IF v_vls_case_state NOT IN ('settled', 'dismissed', 'judgment') THEN
        RAISE EXCEPTION
          'Cannot resolve rental % out of litigation: linked vls.case % is in state % (not settled/dismissed/judgment).',
          NEW.rental_id, v_vls_case_id, v_vls_case_state;
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_event_check_litigation
  BEFORE INSERT ON elektrica.rental_event
  FOR EACH ROW EXECUTE FUNCTION elektrica.rental_event_check_litigation();

-- ---------------------------------------------------------------------------
-- blocked_rentals view: replace the old "JP handoff not wired" entry (now
-- resolved) with real litigation-stage visibility — a rental sitting in
-- needs_served with no case linked yet, or in_litigation while its linked
-- vls.case is stalled (reuses vls.blocked_cases' own JP-trap detection
-- rather than re-deriving it).
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW elektrica.blocked_rentals AS
SELECT id, vehicle_id, renter_id, current_state,
       'needs_demand but assignment_document_ref is missing' AS block_reason
FROM elektrica.rental
WHERE current_state IN ('needs_demand', 'needs_more_information')
  AND assignment_document_ref IS NULL
UNION ALL
SELECT id, vehicle_id, renter_id, current_state,
       'needs_served — no vls.case linked yet (litigation not opened)' AS block_reason
FROM elektrica.rental
WHERE current_state = 'needs_served' AND vls_case_id IS NULL
UNION ALL
SELECT r.id, r.vehicle_id, r.renter_id, r.current_state,
       'in_litigation — linked vls.case stalled: ' || bc.block_reason AS block_reason
FROM elektrica.rental r
JOIN vls.blocked_cases bc ON bc.id = r.vls_case_id
WHERE r.current_state = 'in_litigation';

GRANT SELECT ON elektrica.blocked_rentals TO elektrica_app;

-- elektrica_app also needs SELECT on vls.blocked_cases for the view above
-- to work when queried as that role (views run with the querying role's
-- privileges on the underlying tables unless SECURITY DEFINER — not used
-- here, keeping it simple/auditable).
GRANT SELECT ON vls.blocked_cases TO elektrica_app;
