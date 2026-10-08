# Correctness status — local 0.2.7.dev1 sandbox

The September 27 public review identified six findings in 0.2.4. This local continuation adds explicit regression cases and bounded repairs. It is not a published release and does not replace the later uncommitted Office working tree.

| ID | Local correction | Remaining scope |
|---|---|---|
| F1 | Coordinate-bearing qualifiers are rejected before transformations. | No qualifier mapper; unchanged inspection retains originals. |
| F2 | Typed length, sequence hash, topology and feature-count criteria gate export in the shared service. | Free text remains a caller assessment; unsupported biological criteria are not machine-verified. |
| F3 | A creation convention requiring a modification parent fails in the shared layer. | Reviewed convention vocabulary remains small. |
| F4 | Public iGEM duplicates revalidate parsed identity and all retained evidence blobs, including legacy acquisitions. | Controlled offline connector cases; no live service incident claimed. |
| F5 | Changed metadata or attribution creates a distinct evidence acquisition even if GenBank bytes match. | Source claims and reuse terms still need scientific/user review. |
| F6 | NCBI missing, failed or invalid summaries have per-ID diagnostics and an explicit aggregate summary status. | Discovery is not acquisition or biological validation. |

The handoff's ambiguous-location case now has an explicit inspection-only route. It retains original bytes and warnings; maps show parser interpretations. Unparseable feature locations still fail, and no repaired derivative is generated. Single-record inspection also preserves UTF-8 BOM, line endings and surrounding whitespace in both the GenBank artifact and HTML download.

The optional [two-fragment circular homology operation](reference/homology-assembly.md) is implemented with pinned pydna and explicit junction/annotation maps. It accepts prepared linear inputs, including those derived by explicit [range/orientation planning](reference/fragment-planning.md); it does not design primers, perform cutting, validate temperatures or implement general cloning methods. Repeated homologies, multiple candidate circles and computational limits are explicit failures. Coordinate-bearing qualifiers and inspection-only records remain unsupported for transformations.

See [typed output criteria and inspection](reference/output-criteria.md) for the exact contract. Synthetic regressions and unchanged public-reference inspection demonstrate computational behavior only. Broader assembly methods, annotation inference/reconciliation, 96-member workflows, reviewed host/library/convention packs, private-lab acceptance, cross-agent acceptance and usability baselines remain unfinished. All nine intended host contexts are retained; no biological performance is validated.

Fragment planning requires supplied exact ranges and orientation. It rejects partial features, point locations, uncertain source topology and the existing unsupported feature/qualifier cases. Outside features are listed explicitly; reference locations are projected with a separate audit. It does not infer endpoints or validate physical preparation.

A single whole-record `source` annotation can be projected onto a fragment with an explicit `projected_source` audit; narrower source annotations and other partial features are rejected.

In fragment exports, disjoint projected bibliography ranges remain exact in JSON and GenBank citation remarks; their structured GenBank range is omitted because Biopython 1.86 would expand it to a bounding interval. Simple reference ranges remain structured. Other creation routes retain their previous serializer behavior.
