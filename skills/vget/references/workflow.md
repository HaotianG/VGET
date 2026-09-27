# CLI and job workflow

The command is `vget --workspace /absolute/local/data call TOOL --input /absolute/arguments.json`. Use `--input -` for JSON on stdin. Pass arguments via a file or stdin, not an interpolated shell command containing untrusted objective text. `vget tools` returns executable JSON schemas. With the source bundle, substitute its `vget-cli` launcher for `vget`.

Successful calls emit one JSON object with `schema_version`, `tool`, `status` and `data`. `status=needs_input` is a successful incomplete job state (exit 0). `status=unsupported` is a recorded assessment with no construct. Infeasible assessments return `status=needs_input` and `data.job.status=infeasible`. Tool errors emit `status=error`, structured `error.code/message/details`, and exit 2; unexpected internal failures exit 3. Do not infer a created artifact from exit 0 alone: only an exported job with verified artifact paths is a completed computational result.

Typical tools:

| Need | Tool |
| --- | --- |
| Install bundled reference snapshot | `workspace.init {}` / `vget init`; `empty:true` skips; `demo:true` chooses synthetic fixtures |
| Offline registry catalogue / integrity | `registry.status`, `registry.search`, `registry.install`, `registry.verify` |
| Explicit public freshness check | `registry.check_live` with optional `part_ids` from bundled catalogue; inspect per-record status, not just exit code |
| Public iGEM discovery | `registry.search_public` with a public phrase or exact `name` and bounded page; never send private objectives/notes |
| Import a reviewed iGEM result | `registry.import_public` with exact slug; original GenBank, metadata, authors and source license response are retained |
| Host/source/convention capability context | `context.get` |
| Public NCBI discovery | `library.search_ncbi` with a public phrase; returns up to 20 summaries, no sequence. Search phrase is sent to NCBI; never use private objectives/notes |
| Public NCBI reference | `library.fetch_ncbi` with accession.version; optional expected_raw_sha256; one bounded public GenBank retrieval, no Addgene account |
| Exact local source files | `library.import` with absolute paths and source `lab`, `igem`, `addgene` or `ncbi` |
| Candidate discovery and annotations | `library.search`, `record.inspect` (bases omitted unless explicitly requested) |
| Retained text citation | `evidence.record`, then cite its ID; attribution is not independently verified |
| Lab rules | `convention.draft`, inspect rules/unsupported text, then `convention.activate` only after actual review |
| Objective and interpretation | `job.start`, `job.update` |
| Unsupported/infeasible objective | `job.assess` with a reason; no fabricated exports |
| Resume/history | `job.get`, `job.history` |
| Reasoned exact operations | `job.plan`, then `job.run` with returned `plan.sha256` |
| Verified portable outputs | `artifact.export` into a new directory |
| Compare before/after | `record.compare` |

`job.update` requires the latest `expected_revision`. Decisions are `{field,value,origin,reason,evidence_refs?}` for mode, host_id, name, topology and convention_id. Explicit `convention_id:null` is allowed with a reason. Sources of decisions are `user`, `agent`, `source` or `default`; those are your attributions, not authentication. Name uses 1–48 ASCII letters/numbers/underscore/dot/hyphen starting with alphanumeric. A modify job's topology must match its parent. Inspection uses mode `inspect`, operation `{record_id}` only, source topology (including unknown), and null convention; explicit null host means unassessed. Its name labels the report/package, while the GenBank retains source identity. Host IDs are obtained through context; the toolkit does not infer roles or strains.

Criteria are `{id,text,blocks_export}`. Questions are `{id,question,blocks_export}`; answers are `{question_id,answer,origin}`. Generated completeness questions are addressed to the agent. Resolve them from evidence when possible; do not relay every missing tool field to the user. Custom question IDs must be new, do not use the reserved `field:` prefix. Assumptions are a list of strings. Later updates create new revisions and invalidate the active plan; history retains earlier results.

`job.plan` takes `{job_id,expected_revision,plan}`. The plan contains:

- `operation`: create `{part_ids:[exact IDs in order]}`, or modify `{parent_id,target_feature_id,replacement_id,protected_feature_ids:[exact IDs]}`. An explicit empty protection list is permitted if justified by the objective. Inspection uses `{record_id}` and does not transform sequence or annotations. No raw sequence parameters or generated code.
- `summary`: concise objective interpretation and approach.
- `selections`: one `{record_id,reason,evidence_refs:[existing IDs]}` per unique input; include the modify parent.
- `alternatives`: `{record_id,reason}` entries for rejected inspected records; use an empty list if there is no meaningful alternative.
- `criteria`: exactly one `{id,status,evaluation,evidence_refs}` for every job criterion. Status is `satisfied_by_plan`, `unevaluated` or `unmet`. A blocking criterion must be satisfied by the plan and supported by cited evidence. These are explicitly agent assessments; subsequent software checks are separate.

Evidence references may be record IDs, host IDs, active convention IDs or retained evidence IDs. Metadata/annotation edits invalidate the source fingerprint even if base sequence stays the same. A reference's existence does not prove the inference; evaluate the actual content.

`job.run` checks the current plan hash and pinned sources, then applies the plan through the same core as the GUI. Safe retry of an exported job verifies and reuses artifacts. A failed run retains its plan and diagnostic; it does not become success. After a changed brief/source, inspect and replan. Package tampering is an error, not a reason to silently recreate the receipt.

For an explicitly synthetic evaluation only, `vget --workspace /new/path init --demo` provides arbitrary fixture records and a software convention. Never mix these into a real library or interpret them as functional parts. The ordinary `init` installs the real six-record reference pack offline. `init --empty` leaves the library empty; constructing `Toolkit` without `workspace.init` also leaves a new library empty. Repeated real initialization is idempotent; changed installed pins cause a structured error. The registry is bundled inside the Python wheel and works without a GUI or network.
