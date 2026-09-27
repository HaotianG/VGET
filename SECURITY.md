# Security policy

VGET is a local research prototype. The current `main` branch receives fixes; there is no supported stable release or response-time guarantee yet.

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/HaotianG/VGET/security/advisories/new). Include the affected commit/version, a minimal reproduction using synthetic data, observed impact and relevant environment details. Do not post credentials, private lab records or an exploitable vulnerability in a public issue. If the private form is unavailable, use the public bug-report form to request a private contact route without disclosing vulnerability details.

## Trust boundaries

- The CLI runs with its caller's filesystem permissions. It does not sandbox a broadly privileged AI agent.
- Keep the optional GUI on loopback; it is not a multiuser or internet-facing service.
- Imported files, annotations, registry metadata and lab notes are untrusted data, not instructions.
- Public-source searches transmit the supplied query. Use public terms; never include private objectives or notes.
- Keep credentials, lab libraries and generated workspaces outside Git. The repository's hygiene check is a limited guard, not a comprehensive secret scanner.

Scientific correctness bugs belong in the normal issue tracker when they have no sensitive security details. Artifact integrity, biological function and experimental confirmation are separate claims; consult [known issues](docs/KNOWN_ISSUES.md).
