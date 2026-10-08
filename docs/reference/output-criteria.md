# Computable requirements and original-file inspection

The calling agent records the objective and interprets it. Free-text criteria retain the agent's assessment; they are not executable biological validators. For supported measurable requirements, supply a typed `check` in `job.update`:

```json
{
  "id": "exact_size",
  "text": "The proposed sequence must contain exactly 640 bases.",
  "blocks_export": true,
  "check": {"kind": "length", "value": 640}
}
```

Supported equality checks are `length` (1–100,000), `sequence_sha256` (64 lowercase hexadecimal characters), `topology` (`linear`, `circular`, or `unknown`) and `feature_count` (0–10,000). Unsupported kinds and invalid values are errors. This bounded vocabulary does not parse arbitrary requirements or evaluate biological function.

The plan still includes the criterion's reasoned assessment. After materialization, the shared service independently checks the declared property before creating a design package. A failed blocking check returns `CRITERION_FAILED`, retains the failed job and diagnostic, and produces no completed design or output package. Nonblocking mismatches appear as warnings. The validation receipt includes the expected value, observed value and sequence fingerprint. CLI and direct service callers use this gate.

## Inspect an original with parser warnings

Ordinary imports remain strict. If the purpose is unchanged inspection and a GenBank parser reports an ambiguous or repaired location, explicitly import with:

```json
{"paths": ["original.gbk"], "source": "lab", "inspection_only": true}
```

The toolkit retains the raw bytes, source-file parser warnings and original feature-location expressions. Feature coordinates and maps show the parser's interpretation, with a visible notice. No repair or annotation validity is claimed. Unparseable features, invalid sequence data and incomplete records still fail; this mode does not discard annotations to manufacture an inspection.

Use the existing `inspect` job route. GenBank, the HTML download and the retained original agree byte-for-byte for a single-record source, including BOM, original line endings and surrounding whitespace. Multi-record input selects the matching record and retains the whole source separately. Inspection-only records and their exported inspection records cannot be composed or modified. A reviewed repair requires a separate derivative and comparison; that repair workflow is not implemented here.

## Coordinate qualifiers

Transformations explicitly reject records carrying `transl_except`, `anticodon`, `rpt_unit_range` or `tag_peptide`. These qualifiers encode coordinates separately from the feature location. Unchanged inspection retains them. This conservative restriction prevents stale qualifiers; it does not implement coordinate remapping. See the [INSDC feature-table specification](https://www.insdc.org/submitting-standards/feature-table/) for their definitions.

## Public acquisition revisions

iGEM reuse verifies the parsed record against its original GenBank and retained metadata, authors and license blobs. Missing, changed or inconsistent stored evidence returns `SOURCE_INTEGRITY` without overwriting it. A changed evidence response becomes a separate acquisition even when sequence bytes are identical (`IGEM_EVIDENCE_CHANGED`). Older records remain available. NCBI search reports per-ID unusable summaries and separates complete, partial and wholly unusable summary responses.

## Repeat the offline CLI acceptance

After installing VGET in a virtual environment, run from this source directory:

```sh
python scripts/acceptance_cli.py --output ../acceptance-run-001
```

The runner calls the installed CLI in a fresh workspace. It inspects the six bundled references, creates and modifies two synthetic fixtures, checks the explicit warned-inspection path, and checks a deliberately failing typed requirement. It independently verifies sequence content, composed feature offsets, source bytes, HTML download bytes and package manifests. It uses no live registry calls. Existing output directories are refused so previous evidence remains available.

Each run saves nine paired reports and detailed JSON receipts. These are software acceptance cases; they do not validate cloning methods, biological function, host suitability, private-lab workflows or the report's visual layout.
