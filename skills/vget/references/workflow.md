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
| Explicit two-fragment homology prediction | Create with ordered backbone/insert `part_ids` and `assembly` declaring both terminal overlaps; requires prepared linear inputs, circular output and installed assembly extra. See [contract](../../../docs/reference/homology-assembly.md). |
| Verified portable outputs | `artifact.export` into a new directory |
| Compare before/after | `record.compare` |

`job.update` requires the latest `expected_revision`. Decisions are `{field,value,origin,reason,evidence_refs?}` for mode, host_id, name, topology and convention_id. Explicit `convention_id:null` is allowed with a reason. Sources of decisions are `user`, `agent`, `source` or `default`; those are your attributions, not authentication. Name uses 1–48 ASCII letters/numbers/underscore/dot/hyphen starting with alphanumeric. A modify job's topology must match its parent. Inspection uses mode `inspect`, operation `{record_id}` only, source topology (including unknown), and null convention; explicit null host means unassessed. Its name labels the report/package, while the GenBank retains source identity. Host IDs are obtained through context; the toolkit does not infer roles or strains.

Criteria are `{id,text,blocks_export}`. Questions are `{id,question,blocks_export}`; answers are `{question_id,answer,origin}`. Generated completeness questions are addressed to the agent. Resolve them from evidence when possible; do not relay every missing tool field to the user. Custom question IDs must be new, do not use the reserved `field:` prefix. Assumptions are a list of strings. Later updates create new revisions and invalidate the active plan; history retains earlier results.

For a supported measurable output requirement, add `check:{kind,value}` to the criterion. Kinds are `length`, `sequence_sha256`, `topology` and `feature_count`. The shared service evaluates them on the computed record before export; an inconsistent caller assessment cannot bypass a blocking failure. Free-text criteria still record caller judgments. See [output criteria and inspection](../../../docs/reference/output-criteria.md).

`library.import` accepts explicit `inspection_only:true` for GenBank originals with parser warnings. This retains warnings and original location expressions, preserves the source bytes, and permits unchanged inspection only. Maps show a labeled parser interpretation. Ordinary imports remain strict; no repair is implied. Do not use these records in transformations. Records with coordinate-bearing `transl_except`, `anticodon`, `rpt_unit_range` or `tag_peptide` qualifiers also require unchanged inspection until a qualified mapper is implemented.

`job.plan` takes `{job_id,expected_revision,plan}`. The plan contains:

- `operation`: create `{part_ids:[exact IDs in order]}`, or modify `{parent_id,target_feature_id,replacement_id,protected_feature_ids:[exact IDs]}`. An explicit empty protection list is permitted if justified by the objective. Inspection uses `{record_id}` and does not transform sequence or annotations. No raw sequence parameters or generated code.
- `summary`: concise objective interpretation and approach.
- `selections`: one `{record_id,reason,evidence_refs:[existing IDs]}` per unique input; include the modify parent.
- `alternatives`: `{record_id,reason}` entries for rejected inspected records; use an empty list if there is no meaningful alternative.
- `criteria`: exactly one `{id,status,evaluation,evidence_refs}` for every job criterion. Status is `satisfied_by_plan`, `unevaluated` or `unmet`. A blocking criterion must be satisfied by the plan and supported by cited evidence. These are explicitly agent assessments; subsequent software checks are separate.

Evidence references may be record IDs, host IDs, active convention IDs or retained evidence IDs. Metadata/annotation edits invalidate the source fingerprint even if base sequence stays the same. A reference's existence does not prove the inference; evaluate the actual content.

`job.run` checks the current plan hash and pinned sources, then applies the plan through the same core as the GUI. Safe retry of an exported job verifies and reuses artifacts. A failed run retains its plan and diagnostic; it does not become success. After a changed brief/source, inspect and replan. Package tampering is an error, not a reason to silently recreate the receipt.

For an explicitly synthetic evaluation only, `vget --workspace /new/path init --demo` provides arbitrary fixture records and a software convention. Never mix these into a real library or interpret them as functional parts. The ordinary `init` installs the real six-record reference pack offline. `init --empty` leaves the library empty; constructing `Toolkit` without `workspace.init` also leaves a new library empty. Repeated real initialization is idempotent; changed installed pins cause a structured error. The registry is bundled inside the Python wheel and works without a GUI or network.

## Explicit fragments for homology assembly

Inspect the original source IDs and supplied ranges, then call `fragment.preview` with `{fragment:{record_id,ranges:[{start,end}],orientation:"forward"},include_sequence:false}`. Coordinates are 0-based half-open. A circular origin crossing uses two ordered ranges `[start,length)` then `[0,end)`, with `end < start`. Reverse orientation applies after range selection.

Review the complete annotation comparison. Every feature is retained whole or listed as excluded; partial features fail. Submit `operation:{fragments:[backbone_spec,insert_spec],assembly:{method:"homology",overlaps:[first,second]}}` with selections and evidence referring to the original records. No simultaneous `part_ids`. The plan pins sources and choices; `job.run` rechecks them. `artifact.export` retains original records/bytes and adds `fragment-planning.json` plus an HTML comparison table. Preview IDs are ephemeral, not library IDs.

Endpoint inference, primers and reaction validation remain unsupported. Consequential missing ranges belong in an open blocking job question; unsupported method objectives belong in `job.assess`, without a fabricated export. See the [exact boundary](../../../docs/reference/fragment-planning.md).

A single whole-record `source` annotation can be projected onto a fragment with an explicit `projected_source` audit; narrower source annotations and other partial features are rejected.
