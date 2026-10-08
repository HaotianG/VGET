# Changelog

## 0.2.7.dev1 — explicit fragment preparation (local sandbox)

- Added read-only `fragment.preview` and source-pinned create plans with two explicit source ranges/orientations feeding the existing homology backend.
- Map complete source features through circular-origin selection and reverse orientation; report outside exclusions and audited bibliography range projection. Reject partial features and unsupported point locations.
- Keep original source records/bytes unchanged; intermediates are not stored. Export annotation comparison in HTML and `fragment-planning.json`, with original-to-prepared-to-output feature provenance.
- Avoid misleading GenBank bounding ranges for disjoint projected citations; retain exact scopes as citation remarks and JSON evidence.
- Added frozen synthetic range/orientation fixtures and offline objective-to-artifact CLI replay, including clarification and unsupported primer-design outcomes. Language understanding remains with the caller.

## 0.2.6.dev1 — local assembly milestone, 2026-10-06

- Add optional pinned pydna 5.5.8 backend for two prepared linear fragments with explicit exact terminal homologies and a unique circular product.
- Reject incompatible, repeated/ambiguous, unsupported and over-budget inputs without a composition fallback. Backend prediction runs in a bounded child process.
- Preserve source annotations, qualifiers, strand and bibliography through explicit coordinate maps, including features crossing the circular origin.
- Retain engine/junction/source-coordinate evidence in the package, explain both junctions in HTML and record the computational method in GenBank.
- Apply conventions and typed criteria to the assembled length after overlap deduplication.
- Add frozen synthetic fixtures, regression tests and an installed-CLI assembly acceptance runner. Default composition and original-file inspection remain available without the extra.

This is computational homology prediction. Primer/cutting design, reaction-condition feasibility, host suitability and experimental function are unevaluated.

## 0.2.5.dev1 — local sandbox, 2026-10-05

- Reject transforms involving unsupported coordinate-bearing qualifiers.
- Enforce typed output length, SHA-256, topology and feature-count criteria in the shared service before export.
- Fail creation conventions requiring a parent instead of silently skipping protection.
- Verify complete iGEM acquisitions before reuse; retain changed metadata/attribution as independent revisions.
- Report unusable NCBI summaries per returned identifier.
- Add explicit inspection-only GenBank imports with retained parser warnings and original location expressions. Preserve BOM, whitespace and original download bytes.
- Support explicit source inventories for archive-based repository checks.
- Add a repeatable offline CLI acceptance runner with nine independently checked GenBank/HTML pairs and a negative criterion control.

This prerelease is a local continuation of the published 0.2.4 snapshot. It does not include the unavailable Office Mac working-tree changes or claim biological validation.


## Unreleased

- Licensed original code under MIT while preserving third-party data terms.
- Added a visual README, documentation index, offline example and community templates.
- Adopted the src layout, distribution metadata, dependency updates and documentation/package checks.
- Fixed the GUI default workspace to use the current directory rather than the installed package directory.

- Established the dedicated public Git repository from local prototype 0.2.4.
- Added public installation/contribution documentation, CI, data attribution and the known-issue backlog.
- Made the source launcher independent of the original development workspace.
- No biological operation or review finding is claimed fixed by this repository migration.

## 0.2.4 — local prototype baseline

- Agent-facing CLI/Python tools and portable skill, with decisions, source-pinned plans and paired GenBank/HTML outputs.
- Public NCBI search and exact-accession retrieval; iGEM public search/import and a six-record attributed offline reference pack.
- Existing 115-test suite passed on Python 3.14.4 during the 2026-09-27 review.
- Known gaps include qualifier remapping, executable criterion enforcement and connector/convention inconsistencies. See docs/KNOWN_ISSUES.md.

Earlier work was maintained as local source snapshots rather than Git commits. This repository starts a truthful new history; it does not reconstruct fictitious historical commits.

A single whole-record `source` annotation can be projected onto a fragment with an explicit `projected_source` audit; narrower source annotations and other partial features are rejected.
