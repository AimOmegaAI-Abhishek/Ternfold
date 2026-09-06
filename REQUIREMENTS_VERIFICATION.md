# Requirement-to-verification record

Release baseline: 5 September 2026. The original automated suite passed before the Supabase-only migration. Database integration checks must be rerun against a dedicated Supabase test project before release. Browser evidence: complete A-107 workflow inspected at 1440×900, 390×844 and 320-pixel width; exported version-2 PDF rendered and visually inspected.

Status meanings: **Passed** ran successfully; **Partial** has working baseline behavior but retains a stated pilot gap; **Untested** was not run and is not claimed.

| ID | Source requirement | Status | Verification evidence / remaining limitation |
|---|---|---|---|
| V01 | S §§4–5; X §4 | Passed | Exact A-107 automated and browser values: ₹2,00,000 revenue, ₹17,000 / 8.50%, ₹13,000 erosion. |
| V02 | S §4; X §3 | Passed | Unknown freight blocks; evidenced included freight adds zero once; UI recovery completed. |
| V03 | S §5; X §5 | Passed | Revised terms create v2 at ₹23,000 / 11.50%; below-floor status remains. |
| V04 | S §4; X §7 | Partial | Unit/specification/comparability confirmation blocks publication and manual lines are durable. Detailed conversion/mapping records need a pilot-informed extension. |
| V05 | S §§1,4 | Partial | INR/back-to-back scope rejection and tax-basis confirmation run. A dedicated conditional-rebate/direct-tax capture screen is not included. |
| V06 | S §2; X §7 | Partial | Active supplier-source expiry blocks publication and deleted sources return 410. Conflicting applicability is human-confirmed; there is no structured conflict-resolution object. |
| V07 | S §§4–5 | Passed | Exact Decimal tests include zero revenue, negative quantity, thresholds from unrounded values and 3 × ₹0.335 = ₹1.01. |
| V08 | S §2; X §§5,7 | Partial | Stale saves reject, material edits invalidate review, prior calculations/decisions remain immutable. A simultaneous database-race stress test was not run. |
| V09 | S §§1,6–7 | Passed | Contributor publication denied; outsider and unassigned service admin receive 404 for case/report access. |
| V10 | S §7; X §7 | Passed | Corrupt/wrong-type upload preserves prior files; missing model credentials and extraction failure preserve manual review. Limits are enforced in code. |
| V11 | S §§6–7 | Partial | Duplicate upload/decision retries create no duplicate; model system instruction treats document text as data. No live-provider adversarial test ran without credentials. |
| V12 | S §§2,5; X §§5–7 | Passed | Required Proceed rationale and ₹5,200 actual freight reconcile to ₹22,800 / 11.40% without changing v2. |
| V13 | S §§3,7; X §6 | Partial | PDF values/version/people/rationale match frozen records; refresh/restart and retention deletion passed. External backup restore remains a deployment test. |
| A1 | B §3; S §§1–3 | Passed in baseline | Eligible case creation, persistence, owners/deadlines and upload/line caps are implemented; service deadline remains manual. |
| A2 | B §3; S §§3–4,7 | Passed in baseline | Source viewer, evidence attestations, reviewer confirmation and immutable publication work. |
| A3 | S §7; V §§1,3 | Partial | Tenant authorization, tenant authorization and retention controls, closure and retention work. External encryption/restore and customer terms remain pilot gates. |
| A4 | B §6; X §§2,7–8 | Passed in baseline | Complete desktop/mobile owner journey, separate statuses, keyboard focus, visible recovery and no-change path inspected. |
| A5 | B §5; S §7; V §4 | Partial | Setup, reset, migration, retention and handover instructions exist. Real delivery/effort and commercial evidence do not exist yet. |

## Experience checks

| Check | Status | Observation |
|---|---|---|
| E1 | Passed | Case list and creation show owner, deadlines, scope and next actor. |
| E2 | Passed | Missing freight asks one precise question without losing evidence. |
| E3 | Passed | Comparison explains goods and freight changes using Indian number formatting. |
| E4 | Passed | Relevant supplier source opens beside the financial context. |
| E5 | Passed | Revised terms preserve v1/history and require v2 review. |
| E6 | Passed | Proceed below floor requires and displays Meera’s reason. |
| E7 | Passed | Reconciliation remains separate from the frozen decision. |
| E8 | Passed | Downloaded PDF and copied handoff carry reviewed v2 terms. |
| E9 | Passed in baseline | Upload/model fallback, saved states and mobile layouts give recovery actions. |

## Readiness

- **Ready to demonstrate locally with Supabase:** yes for the synthetic workflow. The full PostgreSQL-backed test suite and the desktop/mobile browser walkthrough passed on 6 September 2026. Live AI completion is not claimed: the configured NVIDIA request reached the provider but timed out, and the verified manual fallback preserved the source and case work.
- **Ready for an assisted external pilot:** no; the external gates in `OPERATIONS.md` are unresolved and deployment tests are unrun.
- **Commercially validated:** no; there is no real payment, customer delivery or repeat-use evidence.

