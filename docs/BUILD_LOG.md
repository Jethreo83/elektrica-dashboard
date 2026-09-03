# Elektrica Dashboard — Build Log

Running log of decisions and file changes, for Jed's review without needing
to re-read full agent transcripts.

## 2026-09-03 — ADR-001 v2 read, build not yet started

- Read `docs/ADR-001-elektrica-rentals-v2.md` (approved) and
  `docs/ELEKTRICA_HANDOFF_2026-09-03.md` in full. Adopting v2 as the
  canonical scope document going forward; my own `docs/original-bot-*.md`
  stays as historical record only.
- Verified current repo state: `migrations/` and `scripts/` are empty — no
  schema or app code exists yet.
- Verified export status: checked `~/Downloads/elektrica_exports/` (Kay's
  `CLAUDE_TO_KAY_006` deliverables). Only
  `DATABASE_MAP_elektrica_SKELETON.md` and `INTEGRATION_INVENTORY.md` exist,
  both explicitly self-marked as PARTIAL/SKELETON, built from static Python
  code analysis, not from actual Sheets access (Elektrica Google OAuth still
  not restored on Kay's host). **No CSV exports of Fleet, the insurance
  carrier database, or insurer-payment history exist yet.**
- Per ADR-001 v2 §6 build order, step 1 ("export & inspect real Sheets")
  blocks step 3+ (writing real `elektrica.vehicle` / `insurance_carrier` /
  `insurer_payment` migration SQL). Holding schema work rather than guessing
  column names, per the ADR's own explicit instruction (§5: "validate field
  names against the real Sheets/Fleet-tab export before finalizing migration
  SQL").
- Flagged a standing-boundary question to Jed directly (not assumed):
  reading VLS migration 002/004 in the VLS repo for the JP-state-machine and
  RLS patterns, as instructed in the ADR/handoff. My profile's hard rule is
  to ask before touching anything VLS-related, even generic schema/trigger
  code with no client data in it, so that's pending his explicit answer.
- No app code, migrations, verify scripts, or deployments created.

**Next up once unblocked:** `elektrica.vehicle`, `elektrica.renter`,
`elektrica.rental` core tables on a Neon staging branch, each with a
companion `verify_NNN.sql`, per the same discipline as the VLS build.
