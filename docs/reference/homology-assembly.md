# Two-fragment circular homology prediction

This optional operation predicts one circular sequence from an already prepared linear backbone and insert. It invokes pinned **pydna 5.5.8** and preserves every supported source feature through an explicit coordinate map. Default creation remains ordered composition. No primer design, physical cutting, implicit linearization, orientation inference, temperature validation or laboratory execution is performed. Explicit [range/orientation preparation](fragment-planning.md) can derive the linear inputs from original sources.

## Install and plan

```sh
python -m pip install '.[assembly]'
```

The calling agent discovers and inspects the exact source records, then uses the normal job route with `mode=create`, `topology=circular` and this operation:

```json
{
  "part_ids": ["exact_linear_backbone_id", "exact_linear_insert_id"],
  "assembly": {
    "method": "homology",
    "overlaps": [
      "ACGTCAGTGCATGACCTAGTACGA",
      "TGCACTGAGATCGTACCGATGCTA"
    ]
  }
}
```

The first overlap is backbone suffix / insert prefix; the second is insert suffix / backbone prefix. The sequences shown are synthetic fixture homologies. They are not primers or recommendations for an experiment. Use explicit input IDs, justified selections and output criteria as usual. `context.get` reports the installed/required backend versions and availability. A missing or different backend is a controlled error; the toolkit never falls back to concatenation.

## Exact supported boundary

- Exactly two distinct linear records in backbone/insert order, with a circular output.
- Two explicit uppercase A/C/G/T homologies, each 20–80 bases. Each must match both terminal ranges, occur exactly once in each source, and be the full terminal homology. Repeated/indistinguishable homologies require clarification.
- A/C/G/T input DNA and nonempty interiors between the homologies; combined input limit 10,000 bases.
- Exact local source feature locations, including compound joins. Existing coordinate-qualifier and inspection-only restrictions apply. No source annotations are clipped or silently dropped.
- A bounded homology graph (16 nodes / 32 edges) and a 12-second child-process limit. A limit error is an unsupported computational outcome, not evidence of biological infeasibility.
- Candidate paths must use both fragments exactly once. Origin rotations and reverse-complement representations of the same double-stranded circle count as one molecule. Multiple distinct circles fail with `ASSEMBLY_AMBIGUOUS`; no product is selected.

The accepted backend sequence is oriented and anchored to backbone base zero, then independently checked against the declared terminal-junction path. It contains each shared overlap once. The backbone position map is unchanged; insert positions map by `(position + backbone_length - first_overlap_length) modulo output_length`. Features crossing the origin become exact compound locations, preserving strand and biological segment order. Source qualifiers remain unchanged. Shared-overlap annotations from both inputs remain separate, with source feature IDs in JSON provenance. Bibliographic ranges are mapped too; original metadata remains in source records.

The JSON evidence records the engine/version, graph counts, declared junction sequences and source/output ranges, source-coordinate maps, origin and orientations. The HTML exposes both junctions directly. GenBank retains the computational method in its comment, mapped annotations and source bibliography. Wet-lab feasibility, host suitability and function remain unevaluated.

## Repeatable acceptance

```sh
python scripts/acceptance_assembly.py --output ../assembly-acceptance-001
```

Use a fresh destination. The runner invokes the installed CLI, checks the frozen sequence/location oracles, source byte retention, GenBank readback, HTML download, junction explanation, safe retry and manifest hashes, and verifies explicit rejection of incompatible and ambiguous inputs. It also tests a false typed length requirement.

The implementation was selected after a bounded comparison with DNA Cauldron 2.0.12 on the same five synthetic fixtures. Both predicted the expected molecule on valid cases; pydna exposed multiple distinct molecules on the repeated-overlap case while the tested DNA Cauldron path returned one. Upstream automatic feature projection also required independent checking, particularly strand on an origin-spanning feature. VGET maps annotations from originals rather than adopting candidate feature lists. These findings apply to those pins and fixtures, not to all workflows supported by either engine.

Sources: [pydna assembly API](https://pydna-group.github.io/pydna/modules/pydna_assembly.html) and [DNA Cauldron GibsonAssembly source](https://edinburgh-genome-foundry.github.io/DnaCauldron/_modules/dnacauldron/Assembly/builtin_assembly_classes/GibsonAssembly.html). Online pydna documentation describes a newer development version; the actual installed 5.5.8 source/API was inspected and exercised here.
