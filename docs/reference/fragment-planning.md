# Explicit fragment planning and annotation comparison

This operation prepares two computational linear fragments from original records for the [circular homology workflow](homology-assembly.md). The caller supplies exact source ranges, orientation and junction homologies. VGET maps coordinates and checks sequence predictions; it does not infer endpoints, perform physical cutting, design primers or validate reaction conditions.

## Preview and plan

Inspect the original record, then preview one fragment:

```json
{
  "fragment": {
    "record_id": "exact_original_record_id",
    "ranges": [{"start": 7, "end": 115}],
    "orientation": "forward"
  },
  "include_sequence": false
}
```

Call `fragment.preview`. Coordinates are **0-based half-open**: the start base is included and the end base is excluded. The result contains a deterministic ephemeral fragment summary and `annotation_comparison`; it does not write a library record. Bases are opt-in. The comparison records original/mapped feature locations, selected/source base counts, outcome, source sequence hash, ranges and orientation. Preview IDs cannot be inspected as library records.

Use a source-pinned `job.plan` with `mode=create`, `topology=circular` and:

```json
{
  "fragments": [
    {"record_id":"original_backbone_id", "ranges":[{"start":7,"end":115}], "orientation":"forward"},
    {"record_id":"original_insert_id", "ranges":[{"start":13,"end":104}], "orientation":"reverse"}
  ],
  "assembly": {"method":"homology", "overlaps":["ACGTCAGTGCATGACCTAGTACGA", "TGCACTGAGATCGTACCGATGCTA"]}
}
```

Numbers and overlaps above illustrate synthetic software fixtures, not a laboratory protocol. Supply your own justified ranges and orientations. The two fragments are in backbone/insert order. Use original record IDs in selections and evidence references; the plan pins their full record fingerprints. Range, orientation and overlap choices enter the plan hash. A changed source or plan cannot be run under the previous hash. No simultaneous `part_ids`, inspection or modification fields are accepted. Exactly two fragment specifications and explicit homology assembly are required.

## Supported coordinates and annotations

A fragment selects one nonempty contiguous range from a known linear/circular source. To cross a circular origin, select exactly two ordered ranges: `[start,source_length)` followed by `[0,end)`, with `end < start`. Reordered/gapped ranges, overlap, repetitions, unknown source topology, empty ranges and full-circle rotations using two ranges are rejected. `[0,source_length)` is an explicit full-record selection. Each prepared fragment is limited to 10,000 bases; the existing backend also limits their combined size to 10,000 bases.

`forward` retains the selected path. `reverse` reverse-complements that entire path. Known feature strands flip while their biological segment order and extracted sequence remain unchanged. Adjacent segments of one join may coalesce after mapping; the comparison retains the original location and records the resulting span. Separate source features are never merged.

A single `source` feature covering the whole original record is a record-scope annotation: when selected partially it is mapped to the whole prepared fragment with unchanged qualifiers and an explicit **projected_source** outcome. Its source/selected base counts and original/mapped locations remain in the audit. This exception does not apply to narrower source annotations or other feature types.

Every other source feature is classified as:

- **retained**: all its bases are selected, with unchanged qualifiers and an exact mapped location;
- **excluded**: all its bases lie outside the selection, with the original feature listed in the comparison;
- **partial**: some bases are selected; preparation fails with `FRAGMENT_PARTIAL_FEATURE` and the complete feature comparison. The engine never clips this annotation.

Exact local join locations are required. Point/between-base locations are rejected with `FRAGMENT_POINT_LOCATION` because their boundary semantics need a reviewed map. Existing inspection-only, fuzzy/remote/order location and coordinate-bearing qualifier restrictions apply to source records, including outside annotations. Reverse preparation requires known strand on retained features; invalid or unknown-strand records fail existing structural checks or `FRAGMENT_STRAND`.

Bibliography text is retained separately from features. Reference ranges are intersected with selected bases and mapped explicitly; the audit retains original and prepared ranges plus `retained`, `projected`, `outside` or `unlocalized` status. An outside citation stays as source bibliography without a prepared range. Biopython 1.86 cannot write disjoint reference scopes faithfully as a structured GenBank reference range. Fragment exports omit that misleading bounding interval and retain the exact projected location in the citation REMARK; JSON metadata/audit retains every segment. Simple citation ranges remain structured. Whole original metadata remains in `source-records.json`; citation retention does not validate a scientific claim for the new construct.

## Execution and artifacts

`job.plan` checks preparation and junction compatibility without invoking the optional backend. `job.run` recomputes preparation, verifies original bytes, invokes the same pinned homology engine and applies typed output criteria to the final assembled record. A missing backend can therefore fail after a valid preview/plan, without an export or fallback.

Original records and source bytes remain unchanged. Intermediate prepared records are not added to the library. The final package contains original records/bytes, `fragment-planning.json`, an HTML annotation comparison, assembly junction evidence and annotated GenBank. Feature JSON retains original → prepared → assembled provenance; GenBank comments describe explicit coordinate preparation and its limits. Safe retries reuse the verified output.

The caller owns ordinary-language interpretation. Record source range facts and inferred choices with their actual origins. If the goal leaves consequential ranges or retained features unspecified, keep a blocking question open. If it requires primer design or reaction validation, record the unsupported objective using `job.assess`; do not claim that this coordinate workflow fulfills it.

## Offline acceptance

```sh
python scripts/acceptance_fragments.py --output ../fragment-acceptance-001
```

Use a fresh output directory and an installation with the `assembly` extra. The runner exercises fixed synthetic objectives through inspection, preview, source-pinned plans and GenBank/HTML export, with literal sequence/location oracles and strand-aware feature extraction. It checks excluded annotations, bibliography, original bytes, comparison evidence, safe retries and manifest hashes, plus partial-cut rejection, invalid ranges, a pending consequential question and an unsupported primer request. `--expect-backend-missing` verifies the base-install path.

This is a scripted CLI workflow with caller-supplied reasoning. It is not an embedded language-understanding test or acceptance of an external agent integration. The new-sequence fixture was absent from the previous backend comparison; this narrow hold-out does not establish performance on representative user objectives or private libraries.
