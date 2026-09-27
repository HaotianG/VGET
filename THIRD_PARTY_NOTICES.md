# Third-party data and dependencies

## Bundled iGEM snapshot

The six records under `vget/data/registry/igem-reporters-2026-09-21/` were retrieved from the official public iGEM Registry API on 2026-09-21. The retained source license response declares [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Original GenBank, metadata and author/license response bytes are retained unchanged. VGET adds the collection manifest, search aliases and quality caveats; these are identified as local curation. No endorsement by iGEM or the original contributors is implied.

| Part | Source-reported authors | Source |
|---|---|---|
| BBa_E0040 | Jennifer Braff | [Registry record](https://api.registry.igem.org/v1/parts/slugs/bba-e0040) |
| BBa_E1010 | Drew Endy | [Registry record](https://api.registry.igem.org/v1/parts/slugs/bba-e1010) |
| BBa_E0020 | Jennifer Braff, Caitlin Conboy | [Registry record](https://api.registry.igem.org/v1/parts/slugs/bba-e0020) |
| BBa_E0030 | Caitlin Conboy, Jennifer Braff | [Registry record](https://api.registry.igem.org/v1/parts/slugs/bba-e0030) |
| BBa_K592009 | Lei Sun | [Registry record](https://api.registry.igem.org/v1/parts/slugs/bba-k592009) |
| BBa_K592012 | Lei Sun | [Registry record](https://api.registry.igem.org/v1/parts/slugs/bba-k592012) |

Exact API URLs, titles, source hashes, dates and attribution are retained in the [collection manifest](vget/data/registry/igem-reporters-2026-09-21/manifest.json) and adjacent original responses. The project code license does not replace the data license. Source descriptions, function and host applicability remain unevaluated.

## Dependencies

Biopython, Flask, openpyxl and their dependencies are installed separately and retain their own licenses. No implementation from OpenCloning, pydna, DNA Chisel, DNA Cauldron, pLannotate, SeqViz or CGView.js is bundled. They are candidates for future evaluated integrations.

## User data

Downloaded records and user-supplied lab data remain in local workspaces, which are ignored by Git. This repository does not include private lab libraries, Addgene account data or user credentials. New datasets require their own attribution and redistribution review.
