# S-XCT-04 — Done

Lane `p2-foundation`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/xct/test_s_xct_04.py: test_upgrade_head_on_empty_database_creates_exactly_one_unique_constraint_on_booking_seat, test_table_and_its_unique_constraint_are_written_in_the_same_single_revision_file, test_no_revision_drops_a_constraint, test_the_guard_is_total_no_where_clause_and_not_a_partial_index all PASS (lane run: 111 passed / 5 failed, none of the 5 is one of these). Also passing: test_the_constraint_refuses_a_second_seller, test_migrated_catalog_is_identical_to_the_catalog_schema_sql_produces (columns, constraints, indexes, grants, owners, sequence grants equal the schema.sql-built database), test_the_orm_mirror_matches_the_migrated_columns. Red-proof: with sa.UniqueConstraint('showtime_id','seat_id') removed from the revision, 4 of these tests went red ('4 failed, 4 deselected'), then the line was restored.

**Note:** The AC is fully proved. The same file also holds test_verify_invariants_sql_passes_as_the_application_role. It is RED, and it is not part of this AC. 36 checks pass. A4 fails only on '(table count mismatch)', because Alembic's alembic_version table sits in public. Defect is in docs/06 checks/verify_invariants.sql (see doc_defects). The test is left red on purpose.
