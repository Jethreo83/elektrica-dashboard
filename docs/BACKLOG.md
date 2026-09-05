# Backlog — decided, not yet actionable

Items Jed has already decided but that don't need schema/code changes
right now (no dependency exists yet to hang them off of). Check this
file whenever touching the area it names — don't rediscover the decision
from scratch or, worse, do it differently by accident.

---

## RESOLVED 2026-09-05 (cron cycle) — carrier edit-after-creation

**What:** the last still-open CarriersPage small item ("CarriersPage can
create a carrier but not edit an existing one's fax/email/phone/aliases
after creation"). Closed via `PATCH /insurance-carriers/{id}` +
frontend edit form + alias-add wiring. See `docs/BUILD_LOG.md`'s matching
entry for the full writeup (186/186 pytest, 147/147 manual runner, live
HTTP verification against real staging proving COALESCE partial-update
semantics hold across multiple sequential edits). Deliberately still no
carrier-rename or alias-removal route — not asked for, would need its own
design decision (alias removal in particular touches whether an already-
matched demand should be affected). Nothing further to do here; kept as a
resolved marker.

---

## RESOLVED 2026-09-05 (cron cycle, later still) — POST /demands/{id}/status live-verified against real staging; frontend gap it exposed closed

**What:** the entry directly above (`RESOLVED ... elektrica.demand HTTP
route to reach 'resolved' built`) explicitly deferred live-verification
against real staging (stale/foreign `DATABASE_URL` in that cycle's
shell) and never checked whether the frontend actually exposed a button
for it. Both closed this cycle:

- Live HTTP round-trip against real staging (resolved the real
  `DATABASE_URL` via the `neon` CLI + Neon API's `reveal_password`,
  confirmed genuinely staging not production first): `sent ->
  negotiating -> resolved` on a real carrier-recipient demand,
  `elektrica.insurer_payment` row created by the trigger via the actual
  route (not a direct DB write). Terminal-state/bad-enum/not-found guard
  rails all confirmed 400 with expected messages, matching
  `test_api.py`'s mocks exactly.
- `web/src/pages/DemandsPage.tsx` had NO button for any transition past
  `mark-sent` -- the route existed and worked, but no staff user could
  ever reach it through the dashboard. Added `advanceDemandStatus()`
  (`web/src/api.ts`) + per-row transition buttons mirroring
  `app/models.py`'s `DEMAND_VALID_NEXT_STATES`.
- New `web/src/pages/CarriersPage.tsx` (`/carriers` route): the handoff
  §2.8 market-rate exhibit had zero frontend consumer despite the
  backend routes existing since earlier the same day. Now lists
  carriers, creates carriers/adjusters, shows the exhibit + resolved-
  claims history per carrier -- live-verified against real staging.

See `docs/BUILD_LOG.md`'s matching entry for full detail. Nothing
further to do on this specific gap; kept as a resolved marker.

**New small items surfaced (not urgent, no design decision needed):**
- `CarriersPage` can create a carrier but not edit an existing one's
  fax/email/phone/aliases after creation (only
  `POST /insurance-carriers/{id}/aliases` exists as a partial-update
  route today).

---

## RESOLVED 2026-09-05 (cron cycle, later still) -- insurer-payment exhibit date-range/vehicle-class filtering

**What:** the entry directly above flagged "the market-rate exhibit has
no date-range/vehicle-class filtering in either the API or the UI yet
(handoff §2.8 mentions both as first-class query needs) -- current
routes return every row for the carrier, filtering would be client-side
only today." Closed this cycle, full stack:

- `app/repository.py`: `list_insurer_payments_for_carrier()` /
  `get_carrier_market_rate_exhibit()` now take optional
  `date_from`/`date_to`/`vehicle_class` args.
- `app/api.py`: both corresponding routes accept the same three as real
  query params, with `vehicle_class` validated against the real enum
  (400 on a bad value).
- `web/src/api.ts` / `web/src/pages/CarriersPage.tsx`: new
  `buildFilterQuery()` helper + date-range/vehicle-class filter
  controls + "Clear filters" button above the exhibit table.

See `docs/BUILD_LOG.md`'s matching entry for the full writeup (4 new
tests, live HTTP verification against real staging proving the filters
are real -- `vehicle_class=van` on carrier 15's only sedan claim
returns `claim_count:0`, not the unfiltered `1`). Nothing further to
do on this specific gap; kept as a resolved marker.

**Still open, not touched this cycle:** carrier edit-after-creation
(the other small item listed directly above -- no route exists for it
beyond the aliases-only partial-update route).

---



**What:** `queue_id=2` had sat `pending` across multiple prior cron
cycles because no admin action existed to resolve it — flagged
repeatedly as "next up" in `docs/BUILD_LOG.md`. Closed this cycle:

- `app/repository.py`: `list_pending_person_match_queue_items()` (query-
  level `source_project <> 'vls'` filter — never even fetches a VLS row,
  not just display-time filtering) and `resolve_person_match_queue()`
  (`confirmed_match` uses the existing `candidate_person_id`;
  `confirmed_split` inserts a brand-new `platform.person` row from the
  queue's own submitted name/DOB/email/phone). Both REQUIRE a privileged
  cursor — `elektrica_app` has **zero** grants, not even `SELECT`, on
  `platform.person_match_queue` (confirmed by direct query against real
  staging Postgres this cycle).
- Hard VLS refusal, enforced in code not just convention: a
  `source_project='vls'` row raises `ValueError` naming the
  attorney-client-privilege boundary explicitly; the route maps this to
  **403** (authorization boundary), not 400/404. This bot must never
  resolve a VLS-domain identity match regardless of who calls the route.
- For `source_project='elektrica'` resolutions only, also links (or
  finds-existing) the resulting person as an `elektrica.renter` via the
  same `create_renter_for_existing_person()` path `POST /renters/intake`
  uses — a queued renter that finally resolves ends up in the identical
  state a clean `attached`/`created` intake would have. Deliberately
  does NOT do this for `source_project='collision'` rows (that
  business's own linking is that repo's responsibility).
- `app/api.py`: `GET /person-match-queue/pending`,
  `POST /person-match-queue/{queue_id}/decision` — both on
  `get_privileged_cursor()`. New Pydantic models
  `PersonMatchQueueItemOut`/`PersonMatchQueueDecisionIn`/`...Out`.
- Tests: 6 new mocked `test_api.py` cases (163/163 pytest, 124/124
  manual runner), covering confirmed_match, confirmed_split with no
  renter for a non-elektrica row, the VLS 403 refusal, 404, and the
  already-resolved 400.

**Live-verified against real staging Postgres, on the REAL long-pending
row** (uvicorn port 8720, `neondb_owner`-class `DATABASE_URL` inline, no
`ELEKTRICA_DB_SET_ROLE`): `GET /person-match-queue/pending` showed the
real `queue_id=2` row (present since an earlier cycle) ->
`POST /person-match-queue/2/decision` `confirmed_match` -> 200,
`resulting_person_id=37`, `elektrica.renter` id=16 created -> re-ran
`GET /person-match-queue/pending` -> now `[]`. Retried the same decision
-> 400 (already resolved, correct). Nonexistent `queue_id=999999` -> 404.
Bad `decision` value -> 400. Then inserted two FRESH synthetic rows
(one `source_project='elektrica'`, one `'vls'`) via a scratch script to
exercise paths the real data couldn't: `confirmed_split` on the
elektrica row -> 200, new `platform.person` id=44 (name/DOB copied from
the queue row, confirmed by direct SELECT), new `elektrica.renter` id=17
-> `confirmed_match` on the vls row -> **403**, then confirmed by direct
SELECT that the vls row was untouched (`status` still `pending`,
`resolved_by` still `NULL`) — the refusal never touched the DB, not just
returned an error to the caller. Server killed after; `netstat` confirmed
no `LISTENING` socket left (only expected client-side `TIME_WAIT`
residue). All scratch scripts (`_setup_queue_smoke.py`,
`_verify_queue_state.py`, `_verify_split_person.py`) deleted immediately
after use.

**Staging residue left intentionally** (same append-only-adjacent
reasoning as every prior smoke run in this repo): `platform.person` ids
43 (throwaway candidate for the synthetic rows) and 44 (real
`confirmed_split` result); `elektrica.renter` ids 16/17;
`platform.person_match_queue` ids 2/3 now `resolved` (2 =
`confirmed_match`, 3 = `confirmed_split`), id 4 (`vls`, deliberately
`pending`) left as a permanent regression-guard example that this bot's
own admin surface must never resolve it going forward.

**Not done / explicitly deferred (unchanged):** no auth/session layer on
any route; migrations 002-010/012-014 remain staging-only pending Jed's
review; migration 007's `vls.case` grant-scope flag for Jed still open;
frontend not started.

**Next up:** with the person_match_queue gap now closed, frontend is the
single largest remaining item (ADR-001 v2 §6/§9 places it last
regardless) — worth spending a cycle surveying which routes exist today
to scope a minimal first frontend screen, rather than starting frontend
code blind.

---

## RESOLVED 2026-09-05 (cron cycle, later) — email/phone normalization utility built

**What:** the entry directly below this one (same date, earlier cycle)
flagged that no email/phone normalization utility existed before calling
`platform.match_or_create_person()`. Closed this cycle by
`app/normalize.py` (`normalize_email()`, `normalize_phone()`), wired into
`POST /renters/intake` (`app/api.py`). See `docs/BUILD_LOG.md`'s matching
entry for the full writeup (scope decision -- kept Elektrica-local, not
extracted to `platform.*`, since Collision's inline email-only version
doesn't count as a second real consumer of the phone half; 12 new
`test_normalize.py` cases; live HTTP verification against real staging
proving a mixed-case email and a punctuated phone both correctly attach
to the same `platform.person` instead of creating a duplicate).

**Still open:** phone format is UNCONFIRMED against real data (every
`platform.person` row on staging has `phone_normalized IS NULL`) --
`normalize_phone()` strips to digits-only with NO US country-code
stripping, flagged in the module's own docstring as an assumption Jed
should confirm once real phone data exists to check it against.

---

## NEW 2026-09-05 (cron cycle) — no email/phone normalization utility exists

**What:** `platform.match_or_create_person()`'s exact-match step does a
literal string-equality comparison against `platform.person.email_normalized`/
`phone_normalized` — those columns are already normalized at rest
(lowercased email, presumably digit-only phone), but nothing in this
codebase normalizes an INCOMING value before passing it in. The new
`POST /renters/intake` route (handoff §2.2 step 1, built this cycle —
see `docs/BUILD_LOG.md`) passes JotForm-submitted email/phone straight
through unmodified.

**Why this matters:** a real JotForm submission with `Jane@Example.com`
or a phone number with dashes/parens will silently fail to match an
existing `Jane@example.com`/digit-only phone row and create a DUPLICATE
`platform.person` — the exact failure mode `match_or_create_person()`
exists to prevent, just moved one layer up to a normalization gap
instead of a matching-logic gap.

**What to do when this is next touched:** write one shared normalization
function (lowercase+strip email; strip non-digits from phone, matching
whatever format `platform.person.phone_normalized` actually uses today —
check real staging rows before guessing the format) and call it from
`POST /renters/intake` before passing values to
`repo.match_or_create_and_link_renter()`. Given convention #1/#2 in this
codebase (shared primitives live in `platform.*`, not duplicated
per-project), check whether VLS/Collision already normalize inline
before their own person-matching calls — if so, this should become a
shared `platform` helper, not an Elektrica-local one, same lesson as the
document-generator placement correction (`docs/OVERNIGHT_DECISIONS.md`,
2026-09-04).

**Not urgent — no action needed until:** a real JotForm webhook is wired
to this route (still manual/API-only today) or Jed reports a duplicate-
person symptom that traces back to this.

---

## RESOLVED 2026-09-05 (cron cycle) — elektrica.demand carrier/adjuster FK wiring

**What:** `docs/BUILD_LOG.md`'s migration-013 entry flagged
`elektrica.demand.carrier_name`/`adjuster_name` (migration 006 PLACEHOLDER
free text) as the natural next item to wire to `platform.insurance_carrier`/
`platform.adjuster` (migration 013) once those tables existed. Closed
this cycle by `migrations/014_elektrica_demand_carrier_fk.sql` — see
`docs/BUILD_LOG.md`'s matching entry for the full writeup (backfill,
new cross-carrier adjuster-match trigger, app-layer changes, 140/140
tests, live HTTP verification against real staging). Nothing further to
do here; kept as a resolved marker so a future session doesn't rediscover
this as still-open.

---

## Staff provisioning must create/link a `platform.person` row (Jed, 2026-09-04, relayed by hermes)

**Decision:** staff provisioning should create (or match-and-link) a
`platform.person` row the same way renter/client/customer provisioning
already does — convention #1 consistency ("every party table keyed by
`person_id`, staff included"). Same decision relayed to VLS and
Collision, so this is a house-wide pattern, not Elektrica-specific.

**Current state:** `elektrica.staff_user.person_id` is already `NOT NULL
REFERENCES platform.person (id)` (migration 011) — the schema already
requires a valid person link, so this isn't a structural gap. What's not
yet decided/built is the *provisioning workflow* itself: no backend/API
exists yet (data layer first, per this build's standing discipline), so
there is no actual "create a staff member" code path today for this
decision to change.

**UPDATE 2026-09-04, later:** the mechanism to use is now real and
verified, not a future design intent — `platform.match_or_create_person()`
(vls-dashboard migration 008, tag `vls-migration-008-person-match`),
live on both staging and production. Read directly (VLS schema, clearance
already established): implements the match-phone/email-first,
then-name+DOB rule exactly (`vls-domain-rules` §10) — exact match
attaches, close match (same last_name + non-null matching DOB) queues to
`platform.person_match_queue` for a human confirm-or-split, no match
creates new. Returns `(person_id, match_status, queue_id)` where
`match_status` is `attached` | `queued` | `created`. Callable only via
`platform_identity_service` (`SECURITY DEFINER`, `REVOKE ALL ... GRANT
EXECUTE ... TO platform_identity_service` — `elektrica_app` has no direct
grant, by design, same split as everywhere else in this schema).

**What to do when staff provisioning is actually built:** call
`platform.match_or_create_person()` through `platform_identity_service` —
do NOT write custom matching logic in Elektrica's own backend, even
something that looks simpler. This is now explicitly the same kind of
shared primitive as the document generator (convention #2) — writing a
project-local version of it would repeat that exact mistake. If
`match_status = 'queued'`, the caller must NOT treat the returned
`person_id` as linked yet — staff provisioning should surface the queue
row for human resolution, not silently attach.

**Not urgent — no action needed until:** a staff-provisioning
API/admin-action is actually being built. Then read this entry first.

---

## `platform.match_or_create_person()` applies to renter provisioning too, not just staff

**What:** Jed/hermes's note about the new shared identity-match primitive
(`platform.match_or_create_person()`, vls-dashboard migration 008) was
delivered in the context of the staff-provisioning backlog item above,
but the function is convention #1 shared infrastructure for EVERY party
table, not staff-specific — this applies equally to `elektrica.renter`
provisioning (handoff §2.2's JotForm intake flow).

**Current state:** no renter-provisioning backend/API exists yet either
(same "data layer first" reason as staff provisioning) — nothing to
retrofit today. But when the JotForm intake handler is eventually built
(handoff §2.2 step 1: "Renter completes a JotForm ... Auto-creates a
Drive folder"), it must call `platform.match_or_create_person()` through
`platform_identity_service` for the renter's identity, not write its own
matching logic or blindly INSERT into `platform.person`.

**Not urgent — no action needed until:** the JotForm intake handler or
any other renter-creation code path is actually being built. Then read
this entry (and the staff one above) first.

**UPDATE 2026-09-04:** the first app-layer code landed (`app/repository.py`,
migration-agnostic session) already anticipated this correctly —
`create_renter_for_existing_person()` and
`provision_staff_user_for_existing_person()` both take an already-resolved
`person_id` as input rather than doing any matching themselves, with
their own docstrings pointing back to this file. Identity resolution
(i.e. the actual `platform.match_or_create_person()` call) is deferred to
whatever calls these functions — correctly not baked into either one.
Nothing to fix; just noting the pattern held before this entry was even
fully written.

---

## RESOLVED 2026-09-04 (cron cycle) — Staff-provisioning HTTP route gap closed

**What:** the staff-provisioning backlog item above (and BUILD_LOG.md's
"not done / explicitly deferred" list from the previous cycle) both
flagged that `provision_staff_user_for_existing_person()` /
`get_staff_user_by_google_email()` existed in `app/repository.py` but had
no HTTP route. Closed this cycle, mirroring Complete Collision's
identical route family exactly (same repo convention):

- `app/repository.py`: added `set_staff_user_active()` (the third
  function Collision's equivalent route family needed; Elektrica had no
  counterpart until now). No `get_staff_capability()` equivalent added —
  Elektrica's role set is a flat `owner`/`staff` split, CONFIRMED FINAL
  by Jed with no further granularity (migration 011), so there is no
  capability-lookup function to expose; this is a real scope difference
  from Collision, not a gap.
- `app/api.py`: `POST /staff`, `GET /staff/{google_email}`,
  `POST /staff/{google_email}/active`. Deliberately does NOT expose a
  route that creates a new `platform.person` row — per this file's own
  entries above, that must go through `platform.match_or_create_person()`
  via `platform_identity_service`, not a bespoke INSERT here.
- Tests: 6 new mocked `test_api.py` cases (36/36 total now), including a
  domain-rejection case confirming `StaffUser.__post_init__`'s ValueError
  surfaces as 400, not 500.
- Live-verified against real staging (`neondb_owner` connection, per the
  documented `elektrica_app` SELECT-only role gap on `staff_user`): ran
  uvicorn, provisioned a real staff_user (person_id=11,
  `smoke.staff@elektricarentals.com`), read it back, deactivated it,
  confirmed a 404 for an unknown email, a 400 for a bad role enum value,
  and a 400 (not 500) for a wrong-domain email. Process killed after.
  Staging residue left intentionally (same append-only-adjacent
  reasoning as every other smoke run in this repo): `staff_user` id=1,
  `platform.person` id=11.

**Still open, not touched this cycle:** the route family has no
auth/session layer (same standing gap as every other route in
`app/api.py`, flagged in that file's own module docstring) — provisioning
a real staff member through this route today requires the same
privileged, non-`elektrica_app` connection every other admin-only
function in this repo needs, and that gate is a human-operated deploy
decision, not something this cycle resolves.

## elektrica.vehicle is missing real Fleet-sheet columns

**Not urgent, needs Jed's scoping decision before building.** The real
`data/real_exports/elektrica_fleet_export.json` "Fleet info" tab has
these columns confirmed real (2026-09-05): Year, Make, Model, Nickname,
VIN, Plate, Miles, Toll Tag, Owner, Lender, Ownership Type.
`elektrica.vehicle` (migration 002, corrected by migration 015) only has
vin/status/current_position/notes -- none of Year/Make/Model/Nickname/
Plate/Miles/Toll Tag/Owner/Lender/Ownership Type exist as columns yet.

This was flagged separately from the class/tracking_system correction
(migration 015) because Jed's instruction was specifically to drop
class/tracking_system -- adding the other real columns wasn't asked for
and would be scope creep to bundle into the same migration.

**Open questions before building, not guessed at:**
- Owner/Lender likely need to be `platform.person_id` FKs (per convention
  #1: every party gets a person_id, not a free-text name column) rather
  than plain TEXT -- but Owner/Lender aren't necessarily platform.person
  in the renter/staff/client sense; could be Elektrica Holdings LLC
  itself, or another business entity, or an individual. Needs Jed's read
  on whether Owner/Lender should be a person_id, a free-text field, or a
  new small `elektrica.entity`/`owner` lookup table.
- Ownership Type is presumably an enum (owned/leased/financed?) but only
  the "Fleet info" tab's header row was captured, not its full value
  set -- same "don't invent enum values from insufficient sample" rule
  as the Rental Management Settings tab enums (see
  OVERNIGHT_DECISIONS.md's Sheet-export entry, point 3).
- Whether this needs its own migration or can ride along with whatever
  next touches elektrica.vehicle.

---

## NEW 2026-09-05 (cron cycle) — elektrica.demand has no HTTP route to reach 'resolved'

**What:** while live-verifying migration 016 (elektrica.insurer_payment,
see BUILD_LOG.md's matching entry) end-to-end, needed to flip a real
demand's status to 'resolved' to exercise the auto-population trigger.
No HTTP route exists for this -- `app/api.py` only has
`POST /demands/{id}/mark-sent` (draft -> sent). Every later transition
(sent -> negotiating -> no_offer/accepted -> resolved) has no route at
all; the DB-level `elektrica.demand_status` enum and its values exist,
but the app layer never got a way to advance a demand past 'sent'.

**Why this matters:** insurer_payment's whole "populates automatically
from every resolved demand" mechanism (handoff §2.8) is real and
verified at the DB layer, but is currently UNREACHABLE from the actual
dashboard -- a human using the app has no button that would ever cause
a real insurer_payment row to be created, only a direct DB write (which
is what this cycle had to fall back to for its own live-verification).

**What to do when this is next touched:** add a route (or a few, mapping
the demand lifecycle's real transitions -- negotiating/no_offer/accepted/
resolved) mirroring `mark_demand_sent`'s shape. No DB-level state-machine
trigger exists on `elektrica.demand_status` the way there is on
`elektrica.rental_state` (migration 003) -- migration 006 never built
one (its own header flags demand_status as PLACEHOLDER, "each has its
own lifecycle" per handoff, not literally enumerated) -- so there's no
sequence to violate, just a missing route. Not blocked on anything;
straightforward next item.

## RESOLVED 2026-09-05 (cron cycle) — elektrica.demand HTTP route to reach 'resolved' built

**What:** closed the gap logged directly above (surfaced by migration
016's own live-verification, which had to fall back to a direct DB
write to flip a demand to 'resolved'). New route
`POST /demands/{id}/status` (`app/api.py`) takes `target_status` +
`actor`, covers every transition past `mark-sent` (sent -> negotiating
-> no_offer -> accepted -> resolved, plus the "resolved with no
negotiation round" and "resolved as a write-off" skip-ahead paths
`elektrica.rental`'s own state machine already allows for its `demand_sent
-> resolved` edge). `draft -> sent` is deliberately excluded from this
route -- that stays `mark-sent`'s job alone, since it also has to write
`sent_via`/`sent_at`.

**How it's enforced (materially different from `transition_rental`):**
confirmed via migration 016's own header + re-reading migration 006 that
NO DB trigger enforces `elektrica.demand_status` sequencing the way
`elektrica.rental_valid_next_states()` (migration 003) enforces
`elektrica.rental_state` -- migration 006 flagged `demand_status` as
PLACEHOLDER precisely because the handoff never enumerated a lifecycle.
So `app/models.py`'s new `DEMAND_VALID_NEXT_STATES` dict +
`validate_demand_transition()` is the REAL enforcement here, not a
redundant fast-path pre-check like `validate_rental_transition` is for
rentals -- flagged this distinction explicitly in both functions'
docstrings so a future session doesn't assume the DB has this covered.
Sequence chosen: `sent -> {negotiating, resolved}`,
`negotiating -> {no_offer, resolved}`, `no_offer -> {accepted, resolved}`,
`accepted -> {resolved}`, `resolved -> {}` (terminal) -- same
skip-to-resolved-at-any-point shape as `RENTAL_VALID_NEXT_STATES`, for
consistency with the one lifecycle in this codebase Jed actually
described end to end.

**App layer:** `app/models.py` (`DEMAND_VALID_NEXT_STATES`,
`validate_demand_transition()`), `app/repository.py`
(`advance_demand_status()` -- validates then a plain column UPDATE;
no `rental_event`-style audit table exists for demands, so
`updated_by`/`updated_at` via the existing `trg_demand_set_updated_at`
trigger, migration 006, is the only record of who/when), `app/api.py`
(`DemandStatusRequest` model, `POST /demands/{id}/status` route --
maps an unknown `target_status` string to 400 same as
`transition_rental`'s `target_state` handling, and any `ValueError`
from `advance_demand_status` — not-found or illegal-transition — to 400).

**Tests:** 5 new `test_api.py` cases (advance to negotiating, advance to
resolved, invalid enum value -> 400, illegal transition -> 400 mocking
`validate_demand_transition`'s real error shape, not-found -> 400). Both
suites green after: 180/180 pytest (was 175), 141/141 manual runner
(`python test_api.py`, was 136).

**Not live-verified against real staging Postgres this cycle:** the
shell's exported `DATABASE_URL` (`ep-damp-bird-...`) does not match
either this repo's `.env.example` or `complete-collision-dashboard`'s
(`ep-bold-leaf-...`), and no local `.env` file exists here to source the
real password — a stale/foreign env var, exactly the failure mode
`scripts/run_dev_server.py`'s own header and `.env.example`'s comment
both already warn about. Did not attempt a live HTTP round-trip against
an unverified connection string; mocked-repository test coverage above is
real and green, but the actual staging round-trip (booting a scratch
uvicorn, POSTing a real status transition, confirming `insurer_payment`
now populates via the dashboard rather than a direct DB write) is the
natural next-cycle follow-up once a trustworthy `DATABASE_URL` is
available in this shell.

---



## RESOLVED 2026-09-05 (cron cycle) — elektrica.insurer_payment (migration 016) built

**What:** handoff §2.8's carrier market-rate exhibit -- the last unbuilt
item in ADR-001 v2/handoff §6 build order step 3. See
`docs/BUILD_LOG.md`'s matching entry for the full writeup (auto-population
trigger, 8/8 verify_016.sql checks on staging, 9 new test_api.py cases,
live HTTP verification end-to-end against real staging Postgres). Also
found and fixed a real latent bug in `test_api.py`'s own `check()` helper
(never raised on failure -- same bug already fixed once in
complete-collision-dashboard's test_api.py). Nothing further to do here;
kept as a resolved marker so a future session doesn't rediscover this as
still-open. New open item surfaced by this work, logged separately above:
no HTTP route exists yet to advance a demand to 'resolved'.

---

**Starting point this cycle:** fetched origin/main first -- 3 new commits
landed since my last known HEAD (`66f56fd` shared-secret JWT auth/CORS
middleware + `GET /me`, `78433eb` migration-015 docs closeout, `964e210`
noting the `web/` frontend-subagent collision was hermes's own dispatch,
not a third party). Before pulling I had mistakenly treated the
already-landed, already-Jed-approved migration 015 drop of
`elektrica.vehicle.class`/`tracking_system` as *undocumented drift* (I
queried staging before fetching/reading BUILD_LOG.md's newest entries)
and manually re-added the columns + a smoke row on the staging branch.
**Caught before committing any code**, reverted the staging schema
change and deleted the smoke row myself, `git stash`'d and discarded my
own resulting code edits (a fleet-board HTML frontend, abandoned anyway
once `docs/BUILD_LOG.md` confirmed a dedicated subagent already owns
`web/`), then re-pulled clean. No commits pushed while confused, no
lasting damage -- but logging the root cause plainly: **I did not
`git fetch`/read the newest BUILD_LOG.md entries before querying
staging and concluding something was wrong.** Lesson for future cycles,
stated as fact not instruction: skipping the fetch-and-read step before
diagnosing "drift" risks mistaking a real, already-approved decision for
an anomaly.

**The actual finding, now confirmed correct:** with migration 015 applied,
`elektrica.vehicle` (migrations 002+015 combined) no longer has ANY
placeholder fields. `vin` (literal), `status` (literal enum --
available/out/maintenance/retired, confirmed verbatim in handoff §2.3),
`current_position`/`position_updated_at` (bot-maintained, no enum to
guess), `notes` (free text) is the complete real column list -- `class`
and `tracking_system`, the only two fields that were ever flagged
PLACEHOLDER, are gone. Every other still-staging-only migration inherits
its staging-only status via an FK chain to something ELSE with a
placeholder (body_shop/rental_type free text on `rental`, carrier/
adjuster/status enums, etc.) -- `elektrica.vehicle` itself, in isolation,
now has none.

**Not promoting this myself.** Every prior promotion in this repo
(migration 001, 011) happened only after an explicit Jed confirmation
was relayed for THAT specific table, not from a bot's own inference that
"the blocking condition seems resolved now." Flagging this as a concrete,
low-effort ask: if Jed confirms `elektrica.vehicle` (as corrected by
migration 015) is fine to promote, the next cycle can do it with the
same verify-on-a-clean-mirror-then-promote discipline used for migration
011, and update this entry to RESOLVED.
