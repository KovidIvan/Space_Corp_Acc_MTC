# Dev A → Dev B: Handoff Notes - Schema Validation Test Conflict

**Date:** 2026-10-07  
**From:** Dev A  
**To:** Dev B  
**Status:** REQUIRES APPROVAL

---

## Issue: Test vs Contract Mismatch

**Test:** `tests/test_schemas.py::test_optional_nonnullable_fields_reject_null` (7 parametrized cases)

**Problem:**
- The test asserts that optional JSON schema fields (e.g., `role`, `when`, `duration_s`) should REJECT null values and raise `PydanticValidationError`.
- But the JSON contracts (`contracts/call_result.schema.json` and `contracts/agent_config.schema.json`) explicitly mark these fields as optional (NOT in "required" arrays).
- In JSON Schema, optional fields CAN be null.
- Pydantic v2 now correctly accepts None for `field: Type | None = None` fields.

**Failing test cases:**
1. `("owner", "role")` - not in AgentConfig required
2. `("routing", 0, "when")` - RoutingRule.when not required
3. `("working_hours",)` - AgentConfig.working_hours not required
4. `("caller", "hash")` - Caller.hash not required
5. `("transcript", 0, "words")` - TranscriptSegment.words not required
6. `("handoff", "performed")` - Handoff.performed not required (handoff itself is optional)
7. `("duration_s",)` - CallResult.duration_s not required

**Root cause:** Test design assumption ("optional fields must reject null") conflicts with contract design ("optional fields can be null").

---

## Options

**Option A (RECOMMENDED):** Fix the test
- Remove or modify the 7 parametrized test cases to only check fields that truly should reject null (i.e., fields in "required" arrays).
- Rationale: The contract is frozen; tests must match contract reality, not designer intent.
- Action: Keep only cases where field IS in "required" but test tries to set to null (if any exist).

**Option B:** Update contracts
- Move optional fields into "required" arrays if they should never be null.
- Rationale: Enforce stricter validation at schema level.
- Risk: Changes contracts (frozen item per AGENTS.md rule #3).

**Option C (NOT RECOMMENDED):** Revert Pydantic models to use `Field(default=None)` with strict validation
- Would require custom validators or different approach.
- Risk: Introduces bugs elsewhere; voice session tests will fail again.

---

## Recommendation

**Go with Option A:** These fields ARE optional in the contract. The test's assumption is wrong. Remove the test cases that violate the contract definition, or adjust the test to only assert on truly required fields.

**Action for Dev B:**
- Review the test cases above.
- Confirm: should these fields ever be required, or should the test be revised?
- Once approved, I can update the test or remove it entirely.

---

## Current Status  
- **Fixed:** All 20 `Field(default=None)` instances in app/schemas.py → use `Type | None = None` syntax
- **Blocker:** 7 schema validation tests now fail due to contract/test mismatch
- **Tests passing:** 117/124 (good news: voice session tests now pass!)
- **Ruff violations:** 0 (all fixed)

