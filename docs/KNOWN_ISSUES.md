# Known issues from the 2026-09-27 review

Baseline: local prototype 0.2.4. The existing 115 tests passed, but the following controlled review cases exposed uncovered behavior. These findings remain open; repository publication does not resolve them.

| ID | Priority | Finding and reproduction | Required correction |
|---|---|---|---|
| F1 | P1 | After prepending six bases, a CDS moves from 1..9 to 7..15 but its `transl_except` location remains 4..6 instead of 10..12. GenBank round-trip still passes. `vget/sequence.py`, feature-shift paths. | Transform supported coordinate-bearing qualifiers with independent expected mappings, or reject the affected transformation. |
| F2 | P1 architecture gap | A blocking free-text criterion requests exactly 1000 bases; a caller assessment marks it satisfied and a 640-base design exports. `vget/contracts.py` and `vget/toolkit.py`, criterion contracts/gates. | Typed computable criteria with validators bound to the materialized output; keep functional claims separately unevaluated. |
| F3 | P2 | Direct service/GUI creation with an active protection rule reports pass although the rule requires a parent and was skipped. Toolkit planning rejects this case. `vget/conventions.py` and `vget/service.py`. | Enforce invariants in the shared domain layer and report inapplicable/unsupported rules explicitly. |
| F4 | P2 | Dynamic iGEM reimport can return `DUPLICATE` after the stored parsed record or source evidence is changed. `vget/registry.py`, duplicate branch. | Validate stored parsed identity and all evidence blobs before reusing an acquisition. Export already catches corrupted blobs later; this does not validate the import response. |
| F5 | P2 | With unchanged GenBank bytes, changed upstream metadata is fetched and discarded with only `DUPLICATE`. | Separate sequence identity from complete acquisition/evidence revision; retain a changed-evidence receipt. |
| F6 | P2 | NCBI search finds an ID but its failed summary is skipped, returning no candidates and no diagnostic. `vget/public_sources.py`. | Per-ID diagnostics or an explicit wholly unusable-response error. |

P1 blocks the affected correctness/acceptance claim. P2 should be resolved during the next focused development milestone. The connector cases use controlled mocked responses, not evidence of an actual public service incident. The deliberately inconsistent caller in F2 demonstrates a missing executable contract; it is not a request for arbitrary natural-language parsing in the CLI.

Additional product gaps: realistic scientific create/modify evaluation, method-specific assembly, reviewed host/library/convention packs, lab mapping-preview onboarding, cross-agent acceptance and usability baselines. Existing end-to-end evidence covers synthetic sequence operations and unchanged public-reference inspection. No biological performance is validated.
