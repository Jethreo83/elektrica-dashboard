-- 009_platform_document_generator.sql
-- Corrects real drift, not a routine feature: relocates the document
-- generator (originally migration 005, built inside the `elektrica`
-- schema) to `platform.*`, per docs/SHARED_CONVENTIONS.md convention #2
-- (from `INSTRUCTION_Jocasta_parallel_build_2026-09-03.md`, Jed via
-- Claude, enforced by hermes/Jocasta):
--
--   "Document generator — ONE shared primitive:
--   (template_id, template_version, merge_data, attachments[]) -> PDF +
--   generation_log_row. Every project calls it. No project builds its own
--   document generator, even for something that looks project-specific
--   ... Placement: build it once shared conventions require it (i.e. when
--   a second real consumer exists — don't build it inside one project's
--   schema 'for now' and plan to move it later)."
--
-- Migration 005's own header comment explicitly reasoned through this
-- exact question and picked the wrong side of it ("build in elektrica for
-- now, move later is a rename not a redesign") — this migration is that
-- rename, corrected as soon as the actual convention (not a guess) became
-- available. Logged as RESOLVED in docs/OVERNIGHT_DECISIONS.md, which also
-- records that this was drift I introduced, not merely an open question
-- Jed needed to adjudicate from scratch.
--
-- MECHANISM: ALTER TABLE/TYPE ... SET SCHEMA. This changes schema
-- membership only — the underlying table/type objects keep their OIDs, so
-- every existing FK (elektrica.demand.generated_document_id ->
-- elektrica.document(id), soon elektrica.rental -> ..., etc.) continues to
-- resolve correctly with zero data movement and zero FK redefinition.
-- Views referencing the moved tables are recreated pointing at the new
-- location (Postgres does not auto-update a view's schema-qualified
-- table references when the underlying table moves schema).

ALTER TABLE elektrica.document_template SET SCHEMA platform;
ALTER TABLE elektrica.document SET SCHEMA platform;
ALTER TABLE elektrica.outbound_log SET SCHEMA platform;

ALTER TYPE elektrica.document_template_family SET SCHEMA platform;
ALTER TYPE elektrica.outbound_channel SET SCHEMA platform;

-- The old elektrica-scoped view referenced elektrica.document/outbound_log
-- by name; drop and recreate under platform now that both tables live
-- there. Same query, new schema.
DROP VIEW IF EXISTS elektrica.documents_never_sent;

CREATE VIEW platform.documents_never_sent AS
SELECT d.id AS document_id, d.source_table, d.source_id, d.generated_at, d.generated_by
FROM platform.document d
LEFT JOIN platform.outbound_log ol ON ol.document_id = d.id
WHERE ol.id IS NULL
  AND d.output_ref IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Grants — elektrica_app is the only real caller today (per the handoff's
-- own observation: "neither VLS nor you have built one yet"), so it gets
-- USAGE + the same SELECT/INSERT it already had, now against the
-- platform-schema location. NOT pre-granting vls_app here: convention #2
-- says build the shared primitive now that it's needed, not "grant to
-- every project speculatively" — vls_app gets its grant in whichever VLS
-- migration adds its first real document-generator caller, same as any
-- other cross-schema access pattern in this codebase (elektrica_app's
-- vls.case/vls.case_event grants in migration 007 were added exactly when
-- Elektrica got a real need, not before).
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA platform TO elektrica_app;  -- likely already granted (RLS SELECT on platform.person, migration 001) but explicit here for clarity
GRANT SELECT, INSERT ON platform.document_template TO elektrica_app;
GRANT SELECT, INSERT ON platform.document TO elektrica_app;
GRANT SELECT, INSERT ON platform.outbound_log TO elektrica_app;
GRANT USAGE, SELECT ON platform.document_template_id_seq TO elektrica_app;
GRANT USAGE, SELECT ON platform.document_id_seq TO elektrica_app;
GRANT USAGE, SELECT ON platform.outbound_log_id_seq TO elektrica_app;
GRANT SELECT ON platform.documents_never_sent TO elektrica_app;

-- document_template_family enum's value set stays exactly as migration
-- 005 defined it (rental_demand, rental_agreement, return_agreement,
-- dv_request_letter — Rentals-only callers for now). Moving schema does
-- not mean inventing VLS-specific template families speculatively; those
-- get added in whichever migration gives VLS its first real caller, per
-- the same "build when needed" discipline.
