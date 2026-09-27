# Getting started

## Install from source

Python 3.11+ on macOS or Linux. Linux CI covers Python 3.11 and 3.14; the initial macOS environment uses 3.14. Native Windows support is not claimed: workspace locking currently uses `fcntl`. There is no published PyPI release yet.

```sh
git clone https://github.com/HaotianG/VGET.git
cd VGET
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
vget tools
```

The command prints a JSON envelope containing tool descriptions and input schemas. Install before importing `vget`; the source lives in `src/`. The root `vget-cli` launcher prefers `.venv/bin/python` and otherwise uses `VGET_PYTHON` or `python3` with an installed package.

## Generate the first paired output

```sh
python examples/inspect_reference.py
```

It initializes `.vget/` with the bundled public snapshot, inspects BBa_E0040 unchanged, and prints absolute paths to GenBank and HTML. Open `report.html` locally; it contains the corresponding GenBank download. Rerunning creates a new job without overwriting previous outputs. The reference's function and host suitability remain unevaluated. No network is used by this example.

For other workspaces:

```sh
vget --workspace .vget init
printf '%s\n' '{}' | vget --workspace .vget call context.get --input -
```

`init --empty` skips the public snapshot; `init --demo` requires an empty library and installs arbitrary software fixtures. Initialization does not grant suitability to a record.

## Connect an agent

Provide the installed command and [skills/vget/SKILL.md](../skills/vget/SKILL.md) through the calling agent's skill mechanism. Keep one explicit workspace throughout a task. Use JSON files or stdin for arguments, rather than shell interpolation of user text:

```sh
printf '%s\n' '{"objective":"Inspect an existing reference and explain its annotations"}' |
  vget --workspace .vget call job.start --input -
```

This starts a job; it does not complete a design. Follow the returned state and [workflow reference](../skills/vget/references/workflow.md). `needs_input` can have exit code 0. No automatic cross-platform skill registration or MCP server is provided.

Python integration uses `from vget.toolkit import Toolkit` and `Toolkit(path).call(tool_name, arguments)`. The calling agent supplies reasoning; the toolkit executes the supported contract.

## Optional GUI

```sh
vget --workspace .vget serve --port 8766
```

Open `http://127.0.0.1:8766`. Keep the server on loopback. Manual designs are separate from agent jobs. On macOS, `scripts/run.command` is an optional convenience launcher after installation.

## Troubleshooting

| Symptom | Check |
|---|---|
| `vget` or module not found | Activate `.venv` and install the project; `src/` is intentionally not injected into `PYTHONPATH`. |
| JSON input error | `--input` expects a file path or `-` for stdin, not an inline JSON string. |
| Empty library | Call `workspace.init` or import files; constructing `Toolkit` alone does not seed records. |
| Unsupported geometry or convention | Read the reported limit; do not strip annotations or relax requirements to force a pass. |
| Public-source failure | Keep the failure explicit; local work and bundled inspection remain available. |

Use synthetic/public inputs in bug reports. `.vget/`, credentials and private datasets must stay out of Git.
