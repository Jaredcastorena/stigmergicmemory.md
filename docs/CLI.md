# Optional helper

made by jared castorena 1728studios llc

All commands use `python3 tools/stigmergy.py --root /path/to/PROJECT ...`. Nothing is installed globally. Run `--help`, `goal --help` or `mail --help` for argument details. Operational output is JSON. CLI v2 adds `ok: true` and `interface_version: 2` to success objects. Failures use `{"ok": false, "interface_version": 2, "error": {"code": "...", "message": "...", "recovery": "..."}}` on stderr, exit 1 (argument errors: exit 2). Branch on `error.code`, not diagnostic wording. `--help` remains human text. Interrupts and interpreter failures are outside this envelope.

| Command | Purpose |
| --- | --- |
| `contract [--operation NAME]` | Fetch one operation with argv/bindings/results; omit NAME for the command and recovery-code index. Does not require initialized project state. |
| `init` | Create private templates and an empty goal state; refuse to overwrite an existing workspace. |
| `resume [--memory-offset N --expect-memory-sha256 HASH --goal-after ID --mail-after ID --limit 3 --max-bytes 6000]` | Read a bounded memory chunk plus goal/mail ID pages. Default serialized success ceiling: 6,000 UTF-8 bytes including newline; allowed 2,048..12,288. |
| `status` | Return the current memory hash, goal revision and last message ID without dumping bodies. |
| `checkpoint --draft FILE --expect-sha256 HASH` | Preserve full old memory plus topic index, then replace it atomically. |
| `goal list --limit 10 --after ID` | List a bounded page of goal IDs, owners and statuses; omit the cursor for the first page. |
| `goal read ID` | Read one goal with its acceptance, evidence and current revision. |
| `goal add --id ID --owner HANDLE --objective TEXT --accept TEXT --next-action TEXT --expect-revision N` | Add a goal. Repeat `--accept` for multiple criteria. |
| `goal update ID --status STATUS --expect-revision N ...` | Update status/owner/next action and add evidence. Blocked/paused states require `--reason`; completed requires `--evidence` (or prior evidence) and `--reviewed`. |
| `mail post --author HANDLE --to HANDLE --kind KIND --title TEXT --body-file FILE --next-owner HANDLE` | Append one message. Optional `--reply-to ID` and repeated `--evidence REF`. Returns the ID to deliver natively. |
| `mail list --after ID --limit 5` | List oldest unread message metadata. Omit `--after` for the beginning, or use `--latest` once for first discovery. |
| `mail read ID --offset 0 --max-chars 2000` | Read an exact message body in bounded Unicode-character chunks. |

`status` hashes and goal revisions are compare-before-write guards, not permissions or authentication. A conflicting write fails; reread and reconcile. The goal state also retains complete previous revisions in the archive directory.

Memory drafts omit the generated footer beginning `<!-- stigmergy:previous-memory -->`; the helper strips that footer if present. It includes the new footer in size validation before writing. Archives are content-addressed and read-only; existing mismatched or writable archives cause a failure.

Mail bodies are limited to 4,000 UTF-8 bytes. Metadata is single-line and bounded. Reserved message delimiters cannot occur inside a body. Replies must reference an existing ID. The helper verifies all message digests before listing or reading, rejects duplicate IDs, and labels authorship unverified. These checks do not prevent a malicious writer from replacing the whole history.

The writer lock is `.stigmergy/.write.lock` and contains PID, host and start time. No command removes a pre-existing lock. After a crash, an operator must verify the owner has ended, inspect the current files and then remove that lock manually before retrying. If a failure leaves a read-only archive but the current file unchanged, retaining that archive is safe.

The starter intentionally has no autonomous watcher, mail rotation daemon, agent-runtime adapters or dependency installer. Native alert delivery belongs to the host; bounded manual mail archival belongs to a reviewed handoff.

## Resume and migration

`resume` is the default operational entrypoint. It does not load archives, public evolution, full goal details or mail bodies. Read the selected goal by ID before work. `snapshot: sequential_reads` explicitly means this is not an atomic multi-file snapshot; retain normal revision/hash guards.

Continue incomplete memory using `memory.next_offset` and `--expect-memory-sha256 memory.sha256`; offsets count Unicode characters. If the hash changes, restart at offset zero and reconcile. Never act on incomplete memory as though it were the full handoff.

The packet trims mail entries, then goal entries, then memory text to meet its byte budget. `more`, `complete` and next cursors report omitted data. A page trimmed to zero retains its incoming cursor: use the dedicated `goal list` or `mail list` command to make progress. Cursor output means returned metadata, not handled work. Route entries before saving their cursor; read only relevant bodies. No automatic cursor persistence or notification is implemented.

v0.1.0 stored records remain v1; no data migration is required. CLI consumers must update from a string `error` to `error.code/message/recovery`. Success payload fields remain at the top level. Read [the execution contract](../agent-contract.json) for exact argv templates and recovery codes, and [record schemas](../schemas/records.schema.json) for structures. Schema checks do not replace semantic helper validation or evidence review.
