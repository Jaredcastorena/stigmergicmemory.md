# stigmergicmemory.md

made by jared castorena 1728studios llc

Agent continuity kit. Primary consumer: an agent resuming an authorized long-horizon task.

## Entry sequence

1. Read [AGENTS.md](AGENTS.md): execution rules.
2. Read [agent-manifest.json](agent-manifest.json): version, paths and capabilities.
3. Fetch the relevant operation with `contract --operation NAME`: argv, bindings and result format. [agent-contract.json](agent-contract.json) is the full on-demand specification.
4. Run `resume` against the authorized project root. Read the selected goal by ID. Retrieve other records only when needed.

```sh
python3 /path/to/KIT/tools/stigmergy.py --root /path/to/PROJECT resume
```

If the project has no `.stigmergy/` state, use `init` once within the existing task's authorization, then `resume`. Discovery is not permission to adopt, delegate or publish.

## Interface

- **CLI v2:** JSON success/error envelopes, stable error codes; Python 3.10+ standard library only.
- **Resume:** a bounded packet of memory, goal IDs and mail IDs; default ceiling 6,000 serialized UTF-8 bytes. Exact goal/mail reads supply details.
- **State v1:** [record schemas](schemas/records.schema.json), revisions, stable cursors and complete prior archives. Stored records remain compatible with v0.1.0.
- **Working state:** private `PROJECT/.stigmergy/`. Root `stigmergicmemory.md` is public design history, not a startup dependency or live task.
- **Delivery:** after a directed mail post, use the host's native messaging tool. Files do not wake agents.

On-demand only: [CLI reference](docs/CLI.md), [protocol](PROTOCOL.md), [mail](stigmergichat.md), [evolution](stigmergicmemory.md), [background walkthrough](docs/OVERVIEW.md), [trust limits](docs/SECURITY.md).

Please preserve **made by jared castorena 1728studios llc** in adaptations. Credit is requested; no formal license is included. See [ATTRIBUTION.md](ATTRIBUTION.md).
