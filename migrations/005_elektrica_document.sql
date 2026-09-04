-- 005_elektrica_document.sql
-- elektrica.document — the shared document generator's storage/log layer,
-- per ADR-001 v2 section 4 ("Recommend building it now, scoped to
-- Elektrica's first real caller (rental demand)") and handoff section 1.3.
--
-- SCOPE NOTE: handoff section 1.3 frames the document generator as a
-- PLATFORM primitive ("(template_id, template_version, merge_data,
-- attachments[]) -> PDF + generation_log_row") meant to be shared with VLS
-- eventually. This migration deliberately builds it inside the elektrica
-- schema for now, NOT in platform.*, because:
--   (a) VLS has not built one yet (confirmed in the handoff itself:
--       "neither VLS nor you have built one yet" per hermes's 2026-09-03
--       message), so there is no second real consumer to extract for yet
--       (ADR-001's own extraction rule: "extracted only when a second
--       consumer exists").
--   (b) Deciding to physically place shared infrastructure in platform.*
--       before a second consumer is proven is exactly the kind of
--       cross-business architecture call this build's discipline holds for
--       human sign-off, not something to default into overnight.
-- This is logged as a queued item in docs/OVERNIGHT_DECISIONS.md, not
-- silently decided. The generation_log contract (template_id/version,
-- merge_data, attachments, output_hash) is written to be extraction-ready:
-- if/when VLS needs the same shape, moving these two tables into
-- platform.* is a rename + grant change, not a redesign.
--
-- No placeholder fields: every column here is a literal requirement from
-- handoff section 1.3's own spec, not a guess against an unseen Sheet.

-- ---------------------------------------------------------------------------
-- elektrica.document_template — versioned templates. Handoff: "Templates
-- are versioned; a generated document records the template version used."
-- ---------------------------------------------------------------------------

CREATE TYPE elektrica.document_template_family AS ENUM (
  'rental_demand',       -- first real caller, per ADR-001 v2 section 4
  'rental_agreement',
  'return_agreement',
  'dv_request_letter'
  -- Deliberately NOT including dv_appraisal_report / total_loss_appraisal_report /
  -- dmv_title_forms / lease_to_own_contract here yet — those belong to
  -- Consulting/Sales domains, out of scope for this migration (ADR-001 v2
  -- section 3: "Consulting ... and Sales ... are separate ADRs / later work").
);

CREATE TABLE elektrica.document_template (
  id                BIGSERIAL PRIMARY KEY,
  family            elektrica.document_template_family NOT NULL,
  version           INTEGER NOT NULL,

  -- The actual template body/reference. Stored as a ref (e.g. a Google Docs
  -- template id, per the existing MASTER_TEMPLATE_ID / TEMPLATE_V3_ID
  -- pattern Kay's static analysis found in the legacy code) rather than
  -- inline content — this migration does not own template authoring.
  template_ref      TEXT NOT NULL,

  is_active         BOOLEAN NOT NULL DEFAULT true,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,

  CONSTRAINT document_template_family_version_unique UNIQUE (family, version)
);

CREATE INDEX idx_document_template_active
  ON elektrica.document_template (family) WHERE is_active = true;

GRANT SELECT, INSERT, UPDATE ON elektrica.document_template TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;

-- ---------------------------------------------------------------------------
-- elektrica.document — generated documents. Handoff: "Attachments are
-- embedded in order ... Every generation writes a log row: who, when,
-- which template version, which source record, output hash."
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.document (
  id                    BIGSERIAL PRIMARY KEY,

  template_id           BIGINT NOT NULL REFERENCES elektrica.document_template (id),

  -- "which source record" — polymorphic on purpose (a document can be
  -- generated from a rental, eventually a demand, etc.). source_table is a
  -- literal table name for now (not a proper polymorphic FK — Postgres
  -- doesn't support that natively, and adding a real FK per source type
  -- can happen once the caller set is stable). Enforced at the application
  -- layer that writes this row, same as the pattern the handoff itself
  -- accepts for provenance-only fields elsewhere (e.g. case_event.source_ref).
  source_table          TEXT NOT NULL,
  source_id             BIGINT NOT NULL,

  -- Merge data frozen at generation time — reproducibility requirement,
  -- same philosophy as VLS's frozen valuation_snapshot pattern (handoff
  -- section 3.4, ADR reused conceptually here for documents generally).
  merge_data            JSONB NOT NULL,

  -- Attachments embedded in order, per handoff literal spec. Each element
  -- is a ref (Drive file id, storage path, etc.) plus a label — shape kept
  -- loose since attachment sourcing (Drive vs local storage) isn't decided.
  attachments           JSONB NOT NULL DEFAULT '[]'::jsonb,

  output_ref            TEXT,   -- Drive file id / storage path of the generated PDF
  output_hash           TEXT,   -- per handoff: "output hash" required on every generation

  generated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  generated_by          TEXT NOT NULL,

  CONSTRAINT document_output_hash_required_once_generated
    CHECK (output_ref IS NULL OR output_hash IS NOT NULL)
);

CREATE INDEX idx_document_source ON elektrica.document (source_table, source_id);
CREATE INDEX idx_document_template ON elektrica.document (template_id);

GRANT SELECT, INSERT ON elektrica.document TO elektrica_app;

-- Generation log is append-only — a generated document's record of what
-- happened at generation time must not be editable after the fact
-- (handoff section 1.3's whole point is an auditable trail).
REVOKE DELETE, UPDATE ON elektrica.document FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.document_forbid_delete()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'elektrica.document is an append-only generation log: DELETE is not permitted (id=%)', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_document_forbid_delete
  BEFORE DELETE ON elektrica.document
  FOR EACH ROW EXECUTE FUNCTION elektrica.document_forbid_delete();

CREATE OR REPLACE FUNCTION elektrica.document_forbid_update()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'elektrica.document is an append-only generation log: UPDATE is not permitted (id=%)', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_document_forbid_update
  BEFORE UPDATE ON elektrica.document
  FOR EACH ROW EXECUTE FUNCTION elektrica.document_forbid_update();

-- ---------------------------------------------------------------------------
-- elektrica.outbound_log — "Outbound delivery ... is a separate step with
-- its own log row, so 'generated but never sent' is visible." (handoff
-- section 1.3). Pulled forward from the ADR's later build-order step
-- because it's a direct, small dependency of the document generator's own
-- completeness story, not because the fuller comms timeline (section 2.6)
-- is being built yet.
-- ---------------------------------------------------------------------------

CREATE TYPE elektrica.outbound_channel AS ENUM ('fax', 'email', 'sms');

CREATE TABLE elektrica.outbound_log (
  id                BIGSERIAL PRIMARY KEY,
  document_id       BIGINT NOT NULL REFERENCES elektrica.document (id),

  channel           elektrica.outbound_channel NOT NULL,
  recipient         TEXT NOT NULL,

  sent_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_by           TEXT NOT NULL,

  delivery_confirmation_ref TEXT,  -- RingCentral fax/SMS confirmation id, email message id, etc.

  CONSTRAINT outbound_log_one_row_per_send UNIQUE (document_id, channel, recipient, sent_at)
);

CREATE INDEX idx_outbound_log_document ON elektrica.outbound_log (document_id);

GRANT SELECT, INSERT ON elektrica.outbound_log TO elektrica_app;
REVOKE DELETE, UPDATE ON elektrica.outbound_log FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.outbound_log_forbid_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'elektrica.outbound_log is append-only: % is not permitted (id=%)', TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_outbound_log_forbid_delete
  BEFORE DELETE ON elektrica.outbound_log
  FOR EACH ROW EXECUTE FUNCTION elektrica.outbound_log_forbid_mutation();

CREATE TRIGGER trg_outbound_log_forbid_update
  BEFORE UPDATE ON elektrica.outbound_log
  FOR EACH ROW EXECUTE FUNCTION elektrica.outbound_log_forbid_mutation();

-- ---------------------------------------------------------------------------
-- "Generated but never sent" visibility — the exact phrase from handoff
-- section 1.3, implemented as a query.
-- ---------------------------------------------------------------------------

CREATE VIEW elektrica.documents_never_sent AS
SELECT d.id AS document_id, d.source_table, d.source_id, d.generated_at, d.generated_by
FROM elektrica.document d
LEFT JOIN elektrica.outbound_log ol ON ol.document_id = d.id
WHERE ol.id IS NULL
  AND d.output_ref IS NOT NULL;  -- only flag documents that finished generating

GRANT SELECT ON elektrica.documents_never_sent TO elektrica_app;
