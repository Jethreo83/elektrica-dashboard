-- 004_elektrica_rental_proposal.sql
-- elektrica.rental_proposal — bot API contract stub, handoff §1.7 / §2.3.
--
-- "Bots write to the app only through a scoped API key against explicitly
-- proposal-shaped endpoints (POST /api/elektrica/rentals/{id}/proposals).
-- Proposals carry source_system, observed_at, evidence ... A proposal is
-- never auto-applied to a legal-record field." This migration is the DB
-- shape only, per ADR-001 v2 build order step 5 ("stub only, the
-- rental-operations bot itself is future work"). No API server exists in
-- this repo yet (data layer first, same discipline as VLS).
--
-- No placeholder fields here: kind/status value sets and column shapes are
-- taken directly from handoff §2.3's literal spec, not guessed from an
-- unseen Sheet. Depends on elektrica.rental (migration 003), which is
-- itself staging-only (FK chain through elektrica.vehicle's placeholder
-- enums — see docs/OVERNIGHT_DECISIONS.md and docs/BUILD_LOG.md). This
-- migration therefore inherits staging-only status mechanically, not
-- because of anything wrong with its own shape.

CREATE TYPE elektrica.proposal_kind AS ENUM (
  'departure',
  'return',
  'dates',
  'tolls'
);

CREATE TYPE elektrica.proposal_status AS ENUM (
  'pending',
  'accepted',
  'rejected'
);

CREATE TABLE elektrica.rental_proposal (
  id                BIGSERIAL PRIMARY KEY,
  rental_id         BIGINT NOT NULL REFERENCES elektrica.rental (id),

  kind              elektrica.proposal_kind NOT NULL,

  -- Free-shape JSON per handoff — different kinds carry different payload
  -- shapes (a "dates" proposal carries start/end candidates, a "tolls"
  -- proposal carries a TollOptics record id + amount, etc). Not typing this
  -- as separate columns per kind: the bot side doesn't exist yet, so
  -- locking a column shape now would be guessing at its future payload.
  proposed_values   JSONB NOT NULL,

  -- Provenance, required on every row — this is a bot-written table by
  -- design (handoff §1.7), never a human-typed default.
  source_system     TEXT NOT NULL,   -- e.g. 'bouncie', 'geofence_email', 'tolloptics'
  evidence          JSONB,           -- e.g. geofence alert message id, TollOptics record id
  observed_at       TIMESTAMPTZ NOT NULL,

  status            elektrica.proposal_status NOT NULL DEFAULT 'pending',
  decided_by        TEXT,
  decided_at        TIMESTAMPTZ,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,

  CONSTRAINT rental_proposal_decision_fields_together
    CHECK (
      (status = 'pending' AND decided_by IS NULL AND decided_at IS NULL)
      OR (status <> 'pending' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)
    )
);

CREATE INDEX idx_rental_proposal_rental_id ON elektrica.rental_proposal (rental_id);
CREATE INDEX idx_rental_proposal_pending ON elektrica.rental_proposal (rental_id) WHERE status = 'pending';

GRANT SELECT, INSERT, UPDATE ON elektrica.rental_proposal TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;

-- ---------------------------------------------------------------------------
-- Immutability rule: a proposal's substantive fields (what was proposed,
-- by whom, from what evidence) never change after creation. The ONLY
-- permitted UPDATE is the one-time pending -> accepted|rejected decision
-- (same restrict-update shape as vls.case_event / elektrica.rental_event).
-- Crucially: accepting a proposal here does NOT write to elektrica.rental —
-- that would violate handoff §1.7 ("never auto-applied to a legal-record
-- field"). A human/future-app-layer action that accepts a proposal is
-- responsible for separately inserting the corresponding elektrica.rental
-- update or elektrica.rental_event row. This table only records the
-- proposal's own lifecycle, on purpose.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elektrica.rental_proposal_restrict_update()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.rental_id       IS DISTINCT FROM OLD.rental_id
     OR NEW.kind          IS DISTINCT FROM OLD.kind
     OR NEW.proposed_values IS DISTINCT FROM OLD.proposed_values
     OR NEW.source_system IS DISTINCT FROM OLD.source_system
     OR NEW.evidence      IS DISTINCT FROM OLD.evidence
     OR NEW.observed_at   IS DISTINCT FROM OLD.observed_at
     OR NEW.created_at    IS DISTINCT FROM OLD.created_at
     OR NEW.created_by    IS DISTINCT FROM OLD.created_by
  THEN
    RAISE EXCEPTION
      'rental_proposal is immutable except for its one-time decision (id=%)', OLD.id;
  END IF;

  IF OLD.status <> 'pending' THEN
    RAISE EXCEPTION
      'rental_proposal decision cannot be changed once made (id=%, status=%)', OLD.id, OLD.status;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_proposal_restrict_update
  BEFORE UPDATE ON elektrica.rental_proposal
  FOR EACH ROW EXECUTE FUNCTION elektrica.rental_proposal_restrict_update();

REVOKE DELETE ON elektrica.rental_proposal FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.rental_proposal_forbid_delete()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'rental_proposal is append-only: DELETE is not permitted (id=%)', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rental_proposal_forbid_delete
  BEFORE DELETE ON elektrica.rental_proposal
  FOR EACH ROW EXECUTE FUNCTION elektrica.rental_proposal_forbid_delete();

-- ---------------------------------------------------------------------------
-- Pending proposals needing a human decision — the queue view the future
-- dashboard's "confirm bot proposal" screen reads from.
-- ---------------------------------------------------------------------------

CREATE VIEW elektrica.pending_rental_proposals AS
SELECT id, rental_id, kind, proposed_values, source_system, evidence, observed_at, created_at
FROM elektrica.rental_proposal
WHERE status = 'pending'
ORDER BY observed_at ASC;

GRANT SELECT ON elektrica.pending_rental_proposals TO elektrica_app;
