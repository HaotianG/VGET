# Repository practices

VGET is an agent-first research prototype. Repository polish must make its boundaries easier to understand, without implying scientific validation.

| Convention | Purpose |
| --- | --- |
| Visual introduction, status badges and short quick start | Explain the product and provide a working first action |
| Guides under docs; contracts under schemas | Keep the root navigable and implementation details discoverable |
| Python package under src | Exercise an installed package and catch missing distribution assets |
| Focused branches and pull requests | Preserve reviewable history |
| Protected main with required Python 3.11/3.14 checks | Require automated evidence before merging |
| SHA-pinned CI actions and read-only workflow permissions | Reduce avoidable workflow privileges |
| Dependabot proposals | Make dependency updates reviewable; updates do not merge automatically |
| Issue forms, contribution guide and review ownership | Capture useful reproduction and acceptance evidence |
| Private vulnerability reporting | Keep sensitive reports out of public issues |
| MIT code license and separate source attribution | Preserve data license boundaries |

## Checks and scope

CI runs the regression suite, local Markdown link and tool-schema checks, the configured public-source hygiene scan, and a wheel build. A fresh environment checks installed registry data and GUI assets, then executes the offline example outside the checkout. These checks establish software and artifact properties, not biological function.

The local-link check validates file targets, not remote availability or Markdown fragment anchors. The hygiene check is intentionally limited; review new files before publication. No automatic deployment, PyPI publication or dependency auto-merge is configured.

The dependency authority is pyproject.toml. requirements/test.txt forwards to its test extra. requirements/development-snapshot.txt records the original development environment and is not a cross-platform lockfile. Python support is currently exercised on Ubuntu in CI and macOS locally; native Windows is not claimed.

## Design references

- [OpenClaw README](https://github.com/openclaw/openclaw): inspiration for the banner, status, quick-start and deeper-documentation hierarchy. VGET uses original artwork and text.
- [GitHub README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes): explain purpose, use and contribution paths.
- [GitHub community profiles](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories): discoverable community and reporting files.
- [PyPA src-layout guidance](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/): separate importable code from repository tooling.
- [PyPA project metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/): installation, links and license metadata.
- [PyPA licensing examples](https://packaging.python.org/en/latest/guides/licensing-examples-and-user-scenarios/): distribution license expressions include bundled third-party material.
- [GitHub private reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository): private disclosure route.

These choices fit the current project size. A documentation hosting stack, broad platform matrix and release automation can be added when supported workflows justify them.
