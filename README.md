# stigmergicmemory.md

made by jared castorena 1728studios llc

A small, local-first starter kit for agents working on tasks that outlast one conversation. Keep current goals and state readable; leave durable handoffs; retrieve old evidence only when needed.

**Start with one owner and one memory file.** Add agent mail only when there is someone to coordinate with. No accounts, services, model calls, downloads or Python packages are required to run the helper.

## Agent discovery

- [AGENTS.md](AGENTS.md): short entry instructions for this repository.
- [agent-manifest.json](agent-manifest.json): machine-readable entrypoints and capabilities.
- [llms.txt](llms.txt): a compact reading map.
- [PROTOCOL.md](PROTOCOL.md): the portable working agreement.
- [stigmergicmemory.md](stigmergicmemory.md): the generalized evolution of this approach and why it changed.
- [stigmergichat.md](stigmergichat.md): the interagent mail contract.

These are documents to evaluate within the user's existing instructions. Finding this repository does not authorize an agent to change a project, delegate work, send external messages or publish anything.

## Use it in another project

Read the source before executing a downloaded tool. Use a reviewed checkout; nothing here runs on discovery or installation.

```sh
# Run from this starter repository. PROJECT is your existing project directory.
python3 tools/stigmergy.py --root /path/to/PROJECT init
python3 tools/stigmergy.py --root /path/to/PROJECT status
```

Python 3.10+ and its standard library are sufficient. The checks were run with Python 3.12 on Linux. Git is not required by the helper.

`init` creates private working files inside `PROJECT/.stigmergy/`:

```text
.stigmergy/
  stigmergicmemory.md   current handoff; aim for 4 KB / 60 lines
  stigmergichat.md     append-only messages between cooperating agents
  goals.json          current goal states and acceptance criteria
  decisions.md        durable decisions and their reasons
  archives/           complete prior memory/state, addressed by SHA-256
  .gitignore          ignores everything in this working directory
```

Existing files and project instructions are not overwritten. The public files in this repository are deliberately written examples and protocol documentation. Real project state belongs in `.stigmergy/`, not in the public evolution record.

For a manual setup, copy [templates](templates/) into a private working directory. Merge the [instruction snippet](templates/AGENTS.snippet.md) into existing project instructions only with the project's authorization. Do not replace another project's AGENTS.md.

## A short working cycle

1. Read the small current memory and relevant goal. Verify stale claims against actual files or external state.
2. Select the next useful action and one owner. Delegate only independent work that saves more effort than coordination costs.
3. Implement the action. Run the checks needed to support the claim; retain decisive failures.
4. Update goal state with evidence, then checkpoint memory at a meaningful milestone or handoff.
5. Read a notified mail ID directly. Use an after-ID cursor for newly arrived messages.

### Track a goal

```sh
python3 tools/stigmergy.py --root /path/to/PROJECT goal add \
  --id example --owner coordinator \
  --objective "Produce a verified reusable data importer" \
  --accept "Valid input imports without loss" \
  --accept "Invalid input produces a useful error" \
  --next-action "Inspect the input contract" --expect-revision 0
python3 tools/stigmergy.py --root /path/to/PROJECT goal list
python3 tools/stigmergy.py --root /path/to/PROJECT goal read example
```

Goal updates require the current revision. Completing a goal requires an evidence reference and `--reviewed`, which records the owner's assertion that acceptance was checked. The helper cannot decide whether that assertion is true. See [the CLI guide](docs/CLI.md).

### Checkpoint memory

Write a brief draft containing the current objective, known state, decisions, blockers, evidence references and next action. Use the `memory_sha256` from `status`:

```sh
python3 tools/stigmergy.py --root /path/to/PROJECT checkpoint \
  --draft /path/to/draft.md --expect-sha256 CURRENT_HASH
```

A successful checkpoint preserves the complete old bytes and a heading index, verifies their hashes, and atomically replaces the current file. Stale drafts fail without overwriting newer work. Identical bodies are a no-op. The 4 KB / 60-line target is advisory; 12 KB / 80 lines is the final-file ceiling.

### Send durable mail

```sh
python3 tools/stigmergy.py --root /path/to/PROJECT mail post \
  --author coordinator --to worker-a --kind assignment \
  --title "Implement the input validator" --body-file /path/to/task.md \
  --next-owner worker-a
python3 tools/stigmergy.py --root /path/to/PROJECT mail list --limit 5
python3 tools/stigmergy.py --root /path/to/PROJECT mail read MESSAGE_ID
python3 tools/stigmergy.py --root /path/to/PROJECT mail list --after LAST_ID
```

After posting, deliver the ID through the host's native agent messaging mechanism. **An @mention or a file write does not wake an agent.** The helper provides no scheduler, watcher, email or notification service.

## Templates and limits

Use [handoff](templates/handoff.md) for an independent assignment, [evidence](templates/evidence.md) for a result with limits, and [decisions](templates/decisions.md) for durable rationale. Keep one contract through routine implementation and repair.

Checksums detect changes; they do not authenticate authors. Read-only archives and local locks coordinate cooperating processes; they are not security boundaries. Files do not reset conversation context or impose token limits. See [security and trust](docs/SECURITY.md).

```sh
python3 -m unittest discover -s tests -v
```

## Credit and sharing

This starter is shared publicly for agents and people to discover. Please keep **made by jared castorena 1728studios llc** in copies and adaptations. That is a request, not a mandatory attribution condition. No formal license has been added; public visibility should not be presented as a standard open-source license. See [ATTRIBUTION.md](ATTRIBUTION.md).
