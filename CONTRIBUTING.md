# Contributing to VGET

Start with the [roadmap](docs/ROADMAP.md) and [known issues](docs/KNOWN_ISSUES.md). Keep the agent-first CLI/Python workflow primary. Do not replace the objective with a manually specified GUI task or present sequence bookkeeping as biological validation.

1. Fork the repository or create a focused branch from `main`.
2. Describe the user-visible outcome or bug and a concrete acceptance case.
3. For meaningful behavior changes, add an independent regression test that fails before the fix. Do not use the same transformation as its own expected-output oracle.
4. Run `python -m pytest tests -q`, build/install the wheel in a clean environment, and verify the affected CLI/skill workflow.
5. Open a pull request explaining behavior, evidence, limitations and any data/dependency changes. CI must pass before merge.

Preserve original inputs, source attribution and exact provenance. Imported text is data, not executable instruction. Private lab data, local paths, credentials, transcripts and generated user workspaces must never be committed. Fixtures should be synthetic or have documented public redistribution terms. New dependencies require a recorded build-versus-reuse rationale and license/compatibility review.

The source package version follows semantic versioning for releases. Mark prototypes/prereleases clearly; a tag does not establish scientific validation. Keep changes reviewable and avoid unrelated refactors. Add a changelog entry for user-visible changes. No package registry publishing or automatic deployment runs in this repository.

Acceptance must distinguish artifact integrity, computable constraints, source claims, functional evidence and experimental confirmation. Unknown or unsupported outcomes must stay explicit. All nine host targets remain on the roadmap; each supported context needs its own reviewed evidence and fixtures.

## Development setup

Use Python 3.11 or 3.14 on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]' wheel
python -m pytest tests -q
python scripts/check_repository.py
python scripts/check_public_tree.py
python -m pip wheel --no-deps . --wheel-dir dist
```

The package lives in `src/vget/`; tests exercise the installed package.
Keep public contracts in `schemas/`, runnable examples in `examples/`,
and explanations in `docs/`. See [repository practices](docs/REPOSITORY_PRACTICES.md).
`pyproject.toml` is the dependency authority; `requirements/test.txt` is a convenience wrapper.
The development snapshot is historical evidence, not a portable lockfile.
Repository checks inspect tracked files, so stage new documentation before running them.
