-- 001_elektrica_renter.sql
-- Elektrica schema bootstrap: elektrica.renter + RLS on platform.person.
--
-- Per ADR-001-elektrica-rentals-v2.md section 4: "Elektrica's
-- elektrica.renter follows the identical pattern" as vls.client
-- (VLS migration 004). No placeholder fields in this file — safe to
-- promote to production independently of migration 002 (vehicle), which
-- carries placeholder enum values pending the real Fleet sheet export.
--
-- platform.person and platform_identity_service already exist (VLS
-- migration 004) — this migration only adds the elektrica schema, its
-- own party table, its own RLS role, and the SELECT policy.

CREATE SCHEMA IF NOT EXISTS elektrica;

-- ---------------------------------------------------------------------------
-- elektrica.renter — Elektrica's own party table, identical pattern to
-- vls.client. A person is visible to elektrica_app only if a row exists
-- here, mirroring vls_app / vls.client.
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.renter (
  id                BIGSERIAL PRIMARY KEY,
  person_id         BIGINT NOT NULL REFERENCES platform.person (id),

  jotform_submission_ref TEXT,  -- handoff §2.2 step 1
  drive_folder_ref       TEXT,  -- handoff §2.2 step 1 ("Auto-creates a Drive folder")

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,

  CONSTRAINT renter_one_row_per_person UNIQUE (person_id)
);

CREATE INDEX idx_renter_person ON elektrica.renter (person_id);

-- ---------------------------------------------------------------------------
-- Row-level security on platform.person, elektrica edition. Identical
-- mechanism to VLS migration 004: a Postgres role per app, elektrica_app
-- can see a person row only if a matching elektrica.renter row exists.
-- platform_identity_service (VLS migration 004) already bypasses RLS for
-- cross-app matching — no new identity-service role needed here.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elektrica_app') THEN
    CREATE ROLE elektrica_app NOLOGIN;
  END IF;
END $$;

GRANT elektrica_app TO neondb_owner;

GRANT USAGE ON SCHEMA platform TO elektrica_app;
GRANT SELECT ON platform.person TO elektrica_app;
GRANT USAGE ON SCHEMA elektrica TO elektrica_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA elektrica TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;

CREATE POLICY elektrica_app_sees_own_renters ON platform.person
  FOR SELECT
  TO elektrica_app
  USING (
    EXISTS (
      SELECT 1 FROM elektrica.renter r WHERE r.person_id = platform.person.id
    )
  );

-- elektrica_app may not write new person rows directly — creation goes
-- through the identity service's match-before-create flow, same rule as
-- vls_app (VLS migration 004). No INSERT grant to elektrica_app on
-- platform.person, enforced by the SELECT-only grant above.

-- Note: ALTER DEFAULT PRIVILEGES not set here, matching VLS migration 004's
-- approach — future elektrica tables need their own GRANT statements in the
-- migration that creates them (see migration 002 for vehicle).
