-- 003_elektrica_rental.sql
-- elektrica.rental — the spine (handoff §2.3), plus its own append-only
-- event log, following the identical pattern to vls.case_event /
-- vls.case (migrations 001/002 in vls-dashboard): state is DERIVED from
-- events, never typed directly; sequence enforced by a trigger-backed
-- valid_next_states() function; direct writes to current_state blocked.
--
-- SCOPE NOTE (important): this migration covers ONLY the elektrica-owned
-- portion of the rental lifecycle (handoff §2.4's flow up through
-- needs_lawsuit / needs_served). It deliberately does NOT wire the JP
-- litigation state machine (answered -> motion_limited_discovery_filed ->
-- discovery_open -> settled/dismissed/judgment). That wiring is still an
-- OPEN QUESTION per ADR-001-elektrica-rentals-v2.md section 7 item 5:
-- "Physical extraction mechanics for the shared JP engine ... same-repo
-- shared package vs. duplicated migration vs. actual service boundary."
-- I am not resolving that architecture question unilaterally overnight
-- without Jed — needs_served is left as a real terminal-for-now state with
-- an explicit TODO comment, not silently forked or duplicated from
-- vls.valid_next_states(). See docs/BUILD_LOG.md for the reasoning.
--
-- Handoff §2.4 also flags: "`finished` (rental) and `finished` (matter)
-- are different states; rename the terminal one `resolved`." Implemented
-- literally: `finished` = vehicle physically returned (mid-flow);
-- `resolved` = the whole matter's terminal state.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

-- Elektrica's own rental/claim lifecycle states, per handoff §2.4's diagram:
--   active -> finished -> needs_demand -> (needs_more_information <-> ) ->
--   demand_sent -> negotiating -> no_offer -> needs_lawsuit -> needs_served
--   -> [JP engine, NOT WIRED HERE] -> resolved
CREATE TYPE elektrica.rental_state AS ENUM (
  'active',
  'finished',                 -- vehicle physically returned; mid-flow, not terminal
  'needs_demand',
  'needs_more_information',   -- rework loop: source disagreement (handoff §2.4)
  'demand_sent',
  'negotiating',
  'no_offer',
  'needs_lawsuit',
  'needs_served',             -- last elektrica-owned state; JP handoff TODO
  'resolved'                  -- terminal for the whole matter
);

CREATE TYPE elektrica.rental_billed_to AS ENUM ('carrier', 'self', 'body_shop');

-- Matches vls.event_source's shape/intent but scoped to Elektrica's actual
-- sources (handoff §1.7, §2.2, §2.6). Not importing vls.event_source itself
-- since 'adobe'/'court_efile' don't apply here and 'jotform' does but with
-- different meaning — narrow by design, same philosophy as VLS's own enum.
CREATE TYPE elektrica.event_source AS ENUM (
  'manual',          -- human-entered via dashboard
  'jotform',         -- intake/completion forms (handoff §2.2)
  'bot_proposal',     -- rental-operations bot proposal, confirmed by human (§1.7)
  'ringcentral',      -- comms timeline events that also mark state (§2.6)
  'system'            -- computed/derived, not a real-world event
);

-- ---------------------------------------------------------------------------
-- elektrica.rental — the spine.
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.rental (
  id                      BIGSERIAL PRIMARY KEY,

  vehicle_id              BIGINT NOT NULL REFERENCES elektrica.vehicle (id),
  renter_id               BIGINT NOT NULL REFERENCES elektrica.renter (id),

  -- PLACEHOLDER SHAPE: body shop and rental type are free text pending real
  -- Rental Management sheet export (Current Rentals / Finished Rentals /
  -- Settings tabs, per Kay's DATABASE_MAP skeleton) — do not assume an enum
  -- value set without seeing real column values.
  body_shop               TEXT,
  rental_type             TEXT,

  billed_to               elektrica.rental_billed_to,

  -- Confirmed dates, per handoff §2.4 step 4 ("Jed opens the rental,
  -- confirms dates"). Bot-proposed dates land in rental_proposal (future
  -- migration), never written here directly.
  start_date              DATE,
  end_date                DATE,

  -- Required before a demand can be generated (handoff §2.3). No document
  -- table exists yet (document generator is future shared infra per ADR-001
  -- v2 section 4) — stored as a Drive file ref for now, TODO: convert to an
  -- FK once elektrica.document exists.
  assignment_document_ref TEXT,

  drive_folder_ref        TEXT,  -- handoff §2.2 step 1
  jotform_submission_ref  TEXT,  -- handoff §2.2 step 1

  -- current_state is a CACHED READ of the latest rental_event, per the same
  -- rule as vls.case.current_state. Never written directly outside the
  -- trigger below — enforced by trigger, not just convention.
  current_state           elektrica.rental_state NOT NULL DEFAULT 'active',

  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by              TEXT NOT NULL,
  updated_by              TEXT NOT NULL
);

CREATE INDEX idx_rental_vehicle ON elektrica.rental (vehicle_id);
CREATE INDEX idx_rental_renter ON elektrica.rental (renter_id);
CREATE INDEX idx_rental_state ON elektrica.rental (current_state);

GRANT SELECT, INSERT, UPDATE ON elektrica.rental TO elektrica_app;

-- ---------------------------------------------------------------------------
-- elektrica.rental_event — append-only, identical pattern to vls.case_event.
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.rental_event (
  id            BIGSERIAL PRIMARY KEY,
  rental_id     BIGINT NOT NULL REFERENCES elektrica.rental (id),
  event_type    elektrica.rental_state NOT NULL,
  event_date    TIMESTAMPTZ NOT NULL DEFAULT now(),

  source        elektrica.event_source NOT NULL,
  source_ref    TEXT,
  notes         TEXT,

  -- Confirmed/unconfirmed pattern from VLS, reused as-is: bot-proposed
  -- events start unconfirmed (handoff §1.7: "A proposal is never
  -- auto-applied to a legal-record field").
  confirmed     BOOLEAN NOT NULL DEFAULT true,
  confirmed_by  TEXT,

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    TEXT NOT NULL,

  CONSTRAINT rental_event_source_ref_required
    CHECK (source IN ('manual', 'system') OR source_ref IS NOT NULL),

  CONSTRAINT rental_event_confirmed_by_required
    CHECK (confirmed = false OR confirmed_by IS NOT NULL)
);

CREATE INDEX idx_rental_event_rental_id ON elektrica.rental_event (rental_id, event_date DESC);
CREATE INDEX idx_rental_event_unconfirmed ON elektrica.rental_event (rental_id) WHERE confirmed = false;

GRANT SELECT, INSERT, UPDATE ON elektrica.rental_event TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;

REVOKE DELETE ON elektrica.rental_event FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.rental_event_forbid_delete()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'rental_event is append-only: DELETE is not permitted (id=%)', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_event_forbid_delete
  BEFORE DELETE ON elektrica.rental_event
  FOR EACH ROW EXECUTE FUNCTION elektrica.rental_event_forbid_delete();

CREATE OR REPLACE FUNCTION elektrica.rental_event_restrict_update()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.rental_id   IS DISTINCT FROM OLD.rental_id
     OR NEW.event_type IS DISTINCT FROM OLD.event_type
     OR NEW.event_date IS DISTINCT FROM OLD.event_date
     OR NEW.source     IS DISTINCT FROM OLD.source
     OR NEW.source_ref IS DISTINCT FROM OLD.source_ref
     OR NEW.notes      IS DISTINCT FROM OLD.notes
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
     OR NEW.created_by IS DISTINCT FROM OLD.created_by
  THEN
    RAISE EXCEPTION
      'rental_event history is immutable: only confirmed/confirmed_by may change (id=%)', OLD.id;
  END IF;

  IF OLD.confirmed = true AND NEW.confirmed = false THEN
    RAISE EXCEPTION
      'rental_event confirmation cannot be revoked once set (id=%)', OLD.id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_event_restrict_update
  BEFORE UPDATE ON elektrica.rental_event
  FOR EACH ROW EXECUTE FUNCTION elektrica.rental_event_restrict_update();

-- ---------------------------------------------------------------------------
-- Sequence validation — elektrica's own portion of the lifecycle only.
-- needs_served has NO valid next state in this function on purpose: that is
-- the explicit TODO boundary where JP-engine wiring will attach once the
-- extraction-mechanics question (ADR §7 item 5) is resolved with Jed.
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
      -- Bidirectional per handoff §2.4 diagram ("(needs_more_information <->)"):
      -- can fall back to needs_demand or proceed once resolved.
      RETURN ARRAY['needs_demand', 'demand_sent']::elektrica.rental_state[];
    WHEN 'demand_sent' THEN
      -- negotiating is the expected path; resolved covers a demand paid in
      -- full with no negotiation round.
      RETURN ARRAY['negotiating', 'resolved']::elektrica.rental_state[];
    WHEN 'negotiating' THEN
      RETURN ARRAY['no_offer', 'resolved']::elektrica.rental_state[];
    WHEN 'no_offer' THEN
      -- needs_lawsuit is the expected path; resolved covers Jed deciding
      -- not to pursue litigation and closing the file.
      RETURN ARRAY['needs_lawsuit', 'resolved']::elektrica.rental_state[];
    WHEN 'needs_lawsuit' THEN
      RETURN ARRAY['needs_served']::elektrica.rental_state[];
    WHEN 'needs_served' THEN
      -- TODO(open question, ADR-001 v2 section 7 item 5): once the JP
      -- engine import mechanics are decided with Jed, this becomes the
      -- handoff point into the imported vls.valid_next_states('jp', ...)
      -- sequence (answered -> motion_limited_discovery_filed ->
      -- discovery_open -> settled/dismissed/judgment), NOT a fork of it.
      -- Allowing a direct resolved transition for now so a rental can still
      -- be closed out manually while that wiring is pending.
      RETURN ARRAY['resolved']::elektrica.rental_state[];
    ELSE
      RETURN ARRAY[]::elektrica.rental_state[];
  END CASE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION elektrica.rental_event_enforce_sequence()
RETURNS TRIGGER AS $$
DECLARE
  v_current_state elektrica.rental_state;
  v_valid elektrica.rental_state[];
BEGIN
  SELECT current_state INTO v_current_state
  FROM elektrica.rental WHERE id = NEW.rental_id
  FOR UPDATE;

  IF v_current_state IS NULL THEN
    RAISE EXCEPTION 'rental_event references unknown rental_id=%', NEW.rental_id;
  END IF;

  v_valid := elektrica.rental_valid_next_states(v_current_state);

  IF NOT (NEW.event_type = ANY(v_valid)) THEN
    RAISE EXCEPTION
      'Invalid state transition for rental % (%): % -> % is not allowed. Valid next states: %',
      NEW.rental_id, v_current_state, v_current_state, NEW.event_type, v_valid;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_event_enforce_sequence
  BEFORE INSERT ON elektrica.rental_event
  FOR EACH ROW EXECUTE FUNCTION elektrica.rental_event_enforce_sequence();

-- After a rental_event is inserted (and passes the sequence check above),
-- advance elektrica.rental.current_state to match. This is the ONLY place
-- current_state is written — direct UPDATEs to it are blocked below.
CREATE OR REPLACE FUNCTION elektrica.rental_advance_state()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM set_config('elektrica.internal_state_write', 'true', true);
  UPDATE elektrica.rental
  SET current_state = NEW.event_type,
      updated_at = now(),
      updated_by = NEW.created_by
  WHERE id = NEW.rental_id;
  PERFORM set_config('elektrica.internal_state_write', 'false', true);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_advance_state
  AFTER INSERT ON elektrica.rental_event
  FOR EACH ROW EXECUTE FUNCTION elektrica.rental_advance_state();

CREATE OR REPLACE FUNCTION elektrica.rental_forbid_direct_state_write()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.current_state IS DISTINCT FROM OLD.current_state
     AND coalesce(current_setting('elektrica.internal_state_write', true), 'false') <> 'true'
  THEN
    RAISE EXCEPTION
      'elektrica.rental.current_state cannot be written directly (rental_id=%). Insert a rental_event instead.',
      OLD.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_forbid_direct_state_write
  BEFORE UPDATE ON elektrica.rental
  FOR EACH ROW
  WHEN (NEW.current_state IS DISTINCT FROM OLD.current_state)
  EXECUTE FUNCTION elektrica.rental_forbid_direct_state_write();

-- ---------------------------------------------------------------------------
-- Blocked list — a query, not required fields, same philosophy as
-- vls.blocked_cases. "Rental needs a demand but has no assignment document"
-- is a real operational block per handoff §2.3 ("assignment_document_id
-- required before a demand can be generated").
-- ---------------------------------------------------------------------------

CREATE VIEW elektrica.blocked_rentals AS
SELECT id, vehicle_id, renter_id, current_state,
       'needs_demand but assignment_document_ref is missing' AS block_reason
FROM elektrica.rental
WHERE current_state IN ('needs_demand', 'needs_more_information')
  AND assignment_document_ref IS NULL
UNION ALL
SELECT id, vehicle_id, renter_id, current_state,
       'needs_served — JP litigation handoff not yet wired (ADR-001 v2 section 7 item 5)' AS block_reason
FROM elektrica.rental
WHERE current_state = 'needs_served';

GRANT SELECT ON elektrica.blocked_rentals TO elektrica_app;
