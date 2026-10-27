# Optional helper

made by jared castorena 1728studios llc

All commands use `python3 tools/stigmergy.py --root /path/to/PROJECT ...`. Nothing is installed globally. Run `--help`, `goal --help` or `mail --help` for argument details. Output is JSON; failures exit nonzero with a short error on stderr.

| Command | Purpose |
| --- | --- |
| `init` | Create private templates and an empty goal state; refuse to overwrite an existing workspace. |
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
