# Architecture and product contract

VGET is an agent-neutral local toolkit. The calling agent resolves objectives, investigates evidence and makes attributable choices. VGET owns supported deterministic operations, source identity, revision checks and paired exports. The optional GUI shares data and serves demonstrations/manual modifications.

| Layer | Current implementation | Intended responsibility |
|---|---|---|
| Agent integration | Portable skill, CLI input schemas, Python dispatcher | Objective resolution, consequential questions, justified plans and honest unsupported results |
| Jobs and plans | Local revision history and exact plan/source fingerprints | Preserve decisions, prevent stale inputs, bind explanations to the executed plan |
| Records and sources | Biopython parsing, local import, bounded public connectors | Original bytes, annotations, attribution and distinct source/evidence revisions |
| Sequence operations | Ordered concatenation, isolated contiguous replacement and optional two-fragment circular homology prediction | Explicitly scoped operations with independently checked feature/qualifier mappings |
| Host/convention context | Nine unevaluated host entries and a small note-rule vocabulary | Reviewed exact context, compatibility evidence and executable convention rules |
| Outputs | GenBank, offline HTML/map, manifest and evidence bundle | One consistent artifact snapshot and truthful computational/biological status |

The core is currently a single Python package with atomic local state writes and workspace locking. It is not a multiuser service or a security boundary for a broadly privileged calling agent. Public network calls are explicit; a public-query field is not a privacy filter.

Confirmed product targets: ordinary-language objectives; both create and modify; annotated GenBank plus explanatory offline HTML; lab-part/convention onboarding; public-source adapters; all nine host contexts; explicit assumptions and targeted clarification. An embedded language model, general GUI editor or distributed architecture is not required.

The nine contexts are E. coli, B. subtilis, S. cerevisiae, Pichia pastoris, Sf9, Sf21, High-5, CHO and HEK293. Names alone establish no compatibility. A future release capability must pin host/variant, library revision, convention revision, supported operation and evaluation evidence.

Important gaps: no cloning-method simulation, typed objective validators, reviewed host packs, general annotation editing or complete coordinate-map contract. See [known issues](KNOWN_ISSUES.md). Keep caller assessment, deterministic checks, reported source function and experimental confirmation separate.

### Explicit fragment preparation

`fragments.py` applies caller-specified 0-based ranges and orientation without modifying source records. `fragment.preview` returns a read-only annotation comparison. A create plan may use exactly two `fragments` with homology assembly instead of `part_ids`; its hash includes exact range/orientation choices and its references pin the original sources. The shared service recomputes preparation before invoking the pinned backend, retains original bytes/records in the package and writes `fragment-planning.json`. Intermediate records have deterministic IDs but are not inserted into the library. Features keep original, prepared and assembled coordinate provenance.

Partial features and point locations are explicit failures; outside features are accounted for. Bibliography text is retained with projected ranges and original ranges in the audit. This is computational coordinate selection, without endpoint inference, physical cutting, primer design or reaction validation.

A single whole-record `source` annotation can be projected onto a fragment with an explicit `projected_source` audit; narrower source annotations and other partial features are rejected.
