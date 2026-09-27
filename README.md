# VGET

An agent-first local toolkit for turning construct objectives into traceable plans, annotated GenBank files and explanatory offline HTML reports.

**Prototype status:** the current core supports exact ordered sequence composition, one contiguous feature replacement, and unchanged GenBank inspection. It does not yet implement general scientific design, cloning-method simulation or validated host compatibility. Known correctness gaps are tracked in [the review backlog](docs/KNOWN_ISSUES.md).

## How it fits an agent

Your existing AI agent interprets the objective, asks consequential questions, investigates sources and submits a justified plan. VGET records those decisions, pins inputs, performs supported sequence operations and exports the paired artifacts. The CLI and Python API are primary; the GUI is optional for inspection and manual edits. No embedded model or model-provider account is required by the toolkit.

```text
User objective → calling agent + VGET skill → decisions and exact plan
             → supported computation + checks → GenBank + HTML + evidence
```

## Install

Python 3.11 or newer:

```sh
git clone https://github.com/HaotianG/VGET.git
cd VGET
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/vget tools
```

The initial local test receipt used Python 3.14.4. GitHub Actions tests the declared minimum and a newer runtime; consult the actual CI result for compatibility evidence. `requirements-lock.txt` records the original development environment, not a portable multi-platform lock.

## Start a workspace

```sh
.venv/bin/vget --workspace .vget init
printf '%s\n' '{}' | .venv/bin/vget --workspace .vget call context.get --input -
```

For a tool call, `--input` accepts a JSON file path; use `--input -` to read JSON from stdin. For example:

```sh
printf '%s\n' '{"objective":"Inspect an existing reference and explain its annotations"}' |
  .venv/bin/vget --workspace .vget call job.start --input -
```

Read the installed CLI help and discovered schemas for each call. `init` installs six bundled public iGEM reporter/chromoprotein records; `init --empty` creates an empty library and `init --demo` explicitly installs arbitrary synthetic software fixtures. A successful import is not proof of biological suitability.

The main agent route is `job.start` → discovery and `job.update` → `job.plan` → `job.run` → `artifact.export`. It records questions, decision origins, assumptions, selected/rejected inputs and source fingerprints. `needs_input` is a valid non-completion result. See [API contract](API-CONTRACT.md) and [skill command guide](skills/vget/references/workflow.md).

## Integrate with an agent

Make the installed `vget` command available and load [skills/vget/SKILL.md](skills/vget/SKILL.md) using your agent's skill mechanism. `vget tools` provides the input schemas. An agent framework can call the CLI or the Python dispatcher:

```python
from vget.toolkit import Toolkit

kit = Toolkit("./my-local-workspace")
kit.call("workspace.init", {})
result = kit.call("job.start", {"objective": "Inspect an existing reference"})
```

No universal plugin registration or MCP transport is implemented. One independent CLI-agent workflow has been exercised with synthetic cases; other agent integrations need their own acceptance checks.

## Outputs

Each completed package includes `construct.gbk`, `report.html`, a manifest and supporting design/provenance records. The standalone HTML includes a map, explanations, assumptions, computational checks and an embedded GenBank download. Biological function, host suitability and experimental confirmation remain separate from structural checks.

Read the known issues before relying on transformed annotations: a coordinate-bearing qualifier can currently remain stale after its feature moves. Also, free-text objective criteria are caller assessments, not independently executable constraints. This is a development prototype.

## Public and local sources

- Local GenBank, FASTA, CSV and XLSX imports.
- Six attributed iGEM reference records included for offline initialization.
- Explicit public iGEM search and selected-record import.
- Explicit NCBI nucleotide search and exact `accession.version` retrieval.
- Addgene: permitted user-file import only; no bulk-access entitlement or credentials are included.

Search calls send the supplied query to the public service. Use public identifiers/terms, not private objectives or lab notes. Local workspaces are ignored by Git; private inputs and generated packages do not belong in pull requests. Public records keep their own terms and attribution; see [third-party notices](THIRD_PARTY_NOTICES.md).

## Optional GUI

```sh
.venv/bin/vget --workspace .vget serve --port 8766
```

Open `http://127.0.0.1:8766`. Manual designs are separate from agent job history. The GUI shares the backend, but a known convention-check discrepancy is tracked in the backlog.

## Development

```sh
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pip wheel --no-deps . --wheel-dir dist
```

Use a feature branch or fork and submit a pull request against `main`. Tests, package installation and public-data hygiene are checked in CI. See [contributing](CONTRIBUTING.md), [architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md) and [changelog](CHANGELOG.md).

The original nine host targets remain E. coli, B. subtilis, S. cerevisiae, Pichia pastoris, Sf9, Sf21, High-5, CHO and HEK293. Present entries record intent only; none is a reviewed biological support claim.

## License

The license for original VGET code is pending owner selection. Bundled public data retains its source-declared license and attribution in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
