-- 010_platform_communication.sql
-- platform.communication — the shared communication timeline, handoff
-- section 1.5 / 2.6 ("RingCentral call transcripts, outbound email/SMS,
-- inbound email — all attached to a domain record ... with provenance"),
-- and SHARED_CONVENTIONS convention #4 ("one inbound-match-then-propose
-- primitive; used by Elektrica (claim #) and Collision (RO/claim).
-- Propose, never auto-file.").
--
-- PLACEMENT (learned from migration 005/009's own lesson, logged in
-- docs/OVERNIGHT_DECISIONS.md and docs/BUILD_LOG.md 2026-09-04): building
-- this inside `elektrica` "for now" and moving it later is exactly the
-- mistake migration 009 had to correct for the document generator. Neither
-- Elektrica nor Complete Collision has built a communication timeline yet
-- (confirmed: docs/SHARED_CONVENTIONS_NOTE.md in complete-collision-dashboard
-- explicitly says "not yet built" on that side too) -- but the convention
-- itself is already written and names BOTH projects as callers, so this is
-- built directly in `platform.*` from the start, not staged in `elektrica`
-- first.
--
-- BUILD ORDER NOTE: the handoff's own section 6 build order lists this
-- step ("... -> outbound log -> comms -> payments -> insurer_payment ...")
-- BEFORE payment/toll (migration 008), which shipped without it. This
-- migration fills that gap now, since it is NOT blocked by the Fleet/
-- carrier/insurer-payment Sheet export dependency that stopped schema work
-- at insurer_payment/adjuster (see docs/OVERNIGHT_DECISIONS.md).
--
-- SCOPE / WHAT IS LITERAL VS INFERRED:
--   Literal from handoff 1.5/2.6: attaches to a domain record with
--   provenance; RingCentral calls matched by renter phone number attach
--   automatically; outbound email/SMS from the app attaches automatically
--   ("it already knows the rental"); inbound carrier email matched by claim
--   number in subject/body is a PROPOSAL pending human confirmation, never
--   auto-filed ("wrong-claim attachment is worse than no attachment").
--   INFERRED (not literal column names -- no real Sheet/table to check
--   against, but no export blocks this either since it's new shared infra,
--   not a migration of an existing legacy sheet): the exact enum value
--   sets below (direction, channel, match_status) and the immutability/
--   restrict-update trigger shape, modeled directly on the already-
--   established elektrica.rental_proposal pattern (migration 004) for
--   consistency, since both are propose-then-confirm primitives.
--
-- Polymorphic source_table/source_id follows the exact pattern already
-- used by platform.document (migration 005/009) -- same primitive family,
-- same shape, so a future collision.job caller needs zero schema change,
-- only a grant.

CREATE TYPE platform.communication_direction AS ENUM ('inbound', 'outbound');

CREATE TYPE platform.communication_channel AS ENUM ('call', 'email', 'sms');

-- 'confirmed': human-verified match, OR an outbound message the app itself
--   authored (it already knows the rental -- confirmed by construction,
--   per handoff 2.6's literal "it already knows the rental" wording).
-- 'proposed': inbound message auto-matched by claim number, pending human
--   confirmation (handoff 2.6's literal "attached as a proposal pending
--   confirmation").
-- 'rejected': human reviewed a proposed match and it was wrong.
CREATE TYPE platform.communication_match_status AS ENUM ('confirmed', 'proposed', 'rejected');

CREATE TABLE platform.communication (
  id                BIGSERIAL PRIMARY KEY,

  -- Polymorphic attachment target -- same pattern as platform.document.
  -- Only real caller today is 'rental' (elektrica.rental.id). No FK
  -- constraint enforced across the polymorphic boundary (same reason
  -- platform.document doesn't FK either) -- application-layer
  -- responsibility to write a valid (source_table, source_id) pair.
  source_table      TEXT NOT NULL,
  source_id         BIGINT NOT NULL,

  direction         platform.communication_direction NOT NULL,
  channel           platform.communication_channel NOT NULL,
  occurred_at       TIMESTAMPTZ NOT NULL,

  from_ref          TEXT,   -- phone number or email address
  to_ref            TEXT,

  subject           TEXT,
  transcript_ref    TEXT,   -- RingCentral transcript / stored body reference, not raw content inline

  -- Provenance -- required on every row, same discipline as
  -- elektrica.rental_event.source_ref and elektrica.rental_proposal.source_system.
  source_system     TEXT NOT NULL,   -- e.g. 'ringcentral', 'app', 'manual'

  match_status      platform.communication_match_status NOT NULL DEFAULT 'confirmed',
  match_evidence    JSONB,           -- e.g. {"matched_claim_number": "..."} for a proposed inbound match
  matched_by        TEXT,
  matched_at        TIMESTAMPTZ,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,

  CONSTRAINT communication_match_fields_together
    CHECK (
      (match_status = 'proposed' AND matched_by IS NULL AND matched_at IS NULL)
      OR (match_status <> 'proposed' AND matched_by IS NOT NULL AND matched_at IS NOT NULL)
    )
);

CREATE INDEX idx_communication_source ON platform.communication (source_table, source_id, occurred_at DESC);
CREATE INDEX idx_communication_proposed ON platform.communication (source_table, source_id) WHERE match_status = 'proposed';

GRANT SELECT, INSERT, UPDATE ON platform.communication TO elektrica_app;
GRANT USAGE, SELECT ON platform.communication_id_seq TO elektrica_app;
-- collision_app is deliberately NOT granted here -- same discipline as
-- migration 009's vls_app deferral: grant added when Complete Collision
-- has an actual caller, not speculatively.

-- ---------------------------------------------------------------------------
-- Immutability: substantive fields are fixed at creation (it's a timeline,
-- "may become evidence" per handoff 2.6). The ONLY permitted UPDATE is the
-- one-time proposed -> confirmed|rejected decision -- identical shape to
-- elektrica.rental_proposal (migration 004) since both are propose-then-
-- confirm primitives.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION platform.communication_restrict_update()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.source_table   IS DISTINCT FROM OLD.source_table
     OR NEW.source_id    IS DISTINCT FROM OLD.source_id
     OR NEW.direction    IS DISTINCT FROM OLD.direction
     OR NEW.channel      IS DISTINCT FROM OLD.channel
     OR NEW.occurred_at  IS DISTINCT FROM OLD.occurred_at
     OR NEW.from_ref     IS DISTINCT FROM OLD.from_ref
     OR NEW.to_ref       IS DISTINCT FROM OLD.to_ref
     OR NEW.subject      IS DISTINCT FROM OLD.subject
     OR NEW.transcript_ref IS DISTINCT FROM OLD.transcript_ref
     OR NEW.source_system IS DISTINCT FROM OLD.source_system
     OR NEW.created_at   IS DISTINCT FROM OLD.created_at
     OR NEW.created_by   IS DISTINCT FROM OLD.created_by
  THEN
    RAISE EXCEPTION
      'platform.communication is immutable except for its one-time match decision (id=%)', OLD.id;
  END IF;

  IF OLD.match_status <> 'proposed' THEN
    RAISE EXCEPTION
      'platform.communication match decision cannot be changed once made (id=%, match_status=%)', OLD.id, OLD.match_status;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_communication_restrict_update
  BEFORE UPDATE ON platform.communication
  FOR EACH ROW EXECUTE FUNCTION platform.communication_restrict_update();

REVOKE DELETE ON platform.communication FROM PUBLIC;

CREATE OR REPLACE FUNCTION platform.communication_forbid_delete()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'platform.communication is append-only: DELETE is not permitted (id=%)', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_communication_forbid_delete
  BEFORE DELETE ON platform.communication
  FOR EACH ROW EXECUTE FUNCTION platform.communication_forbid_delete();

-- ---------------------------------------------------------------------------
-- Queue view -- proposed inbound matches awaiting human confirmation, same
-- philosophy as elektrica.pending_rental_proposals.
-- ---------------------------------------------------------------------------

CREATE VIEW platform.pending_communication_matches AS
SELECT id, source_table, source_id, direction, channel, occurred_at,
       from_ref, to_ref, subject, match_evidence, source_system
FROM platform.communication
WHERE match_status = 'proposed'
ORDER BY occurred_at ASC;

GRANT SELECT ON platform.pending_communication_matches TO elektrica_app;
