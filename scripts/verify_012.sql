-- Verification for migration 012 (fix: elektrica_app sequence grants
-- migration 008 missed for toll_id_seq / compliance_item_id_seq).
-- Grant-only migration -- no new tables/rows, so this checks the actual
-- privilege via has_sequence_privilege() rather than
-- information_schema.usage_privileges (that view only ever reports the
-- USAGE privilege type by definition -- it will never show SELECT even
-- when granted, so it's the wrong tool to confirm this fix fully).

SELECT
  'elektrica.toll_id_seq' AS sequence_name,
  has_sequence_privilege('elektrica_app', 'elektrica.toll_id_seq', 'USAGE') AS has_usage,
  has_sequence_privilege('elektrica_app', 'elektrica.toll_id_seq', 'SELECT') AS has_select
UNION ALL
SELECT
  'elektrica.compliance_item_id_seq',
  has_sequence_privilege('elektrica_app', 'elektrica.compliance_item_id_seq', 'USAGE'),
  has_sequence_privilege('elektrica_app', 'elektrica.compliance_item_id_seq', 'SELECT');
-- Expected: both rows show has_usage=t, has_select=t.
