# Memory of the memory system

made by jared castorena 1728studios llc

This is a curated public evolution record, not a transcript, live task state or private project history. It describes lessons that apply across software, research, writing, analysis and other long-running agent tasks.

## Purpose

Maintain continuity when a task outlasts a context window or changes owners. Preserve goals, constraints, decisions, evidence and the next useful action without loading the entire history on every resume.

## How it evolved, and why

1. **One durable note.** A root memory file captured the task and next step. It made resumptions possible, but eventually mixed current facts with old plans and large result dumps.
2. **Shared coordination.** A mailbox and named owners made parallel work visible. Timed check-ins and acknowledgment chains then added overhead without reliably waking recipients.
3. **A smaller active memory.** Current state became a concise handoff. Long results moved into referenced evidence, with explicit distinctions between proposed, implemented and verified work. A short summary alone was not enough: the underlying result had to remain available.
4. **Complete archival before compression.** Before shortening memory, preserve all old bytes, verify SHA-256, and record exact heading ranges. Immutable-by-convention snapshots and indexes made references stable. A summary is an index into evidence, not a replacement for it.
5. **Directed delivery and bounded retrieval.** Mail IDs, reply-to links and after-ID cursors replaced broad history reads. Durable messages were paired with native agent delivery. Mentions and promised future check times were recognized as insufficient to wake workers.
6. **Coordination proportional to work.** One owner became the default. Independent workers received narrow packets and exclusive files. One shared contract covered routine implementation and repair. Result messages replaced acknowledgment loops, duplicate reports and idle monitoring.
7. **Honest verification and privacy.** Decisive failures and limitations stayed recorded. Checks were selected for the changed behavior. Working records and all private references stayed out of public source and exports; public summaries were written separately.
8. **Portable starter.** The reusable rules became templates plus optional dependency-free tooling. Goals gained explicit ownership, acceptance and state revisions. Repository discovery became an invitation to evaluate the protocol, not automatic authorization to install or act.

9. **Executable agent entrypoint.** A human tutorial was too indirect for resuming agents. The default route became an execution contract, structured record schemas, byte-bounded resume packets and stable recovery codes. History moved off the startup path; readable prose remained an optional reference.

10. **Explicit reuse terms.** The starter adopted the standard MIT license so agents can identify reuse terms through an SPDX identifier and a canonical license file. The additional credit-line request remained voluntary.

## Decisions retained

- Aim for 4 KB / 60 lines of current memory; avoid cosmetic rewrites just to meet an advisory target.
- Archive complete previous content before compression; reject stale writes.
- Use full records on disk and narrow references in context.
- Mail meaningful assignments, blockers, interface changes and completions once.
- Verify actual outcomes. A green status or a checksum is not proof of factual correctness.
- Keep private task state separate from deliberately published examples.

## Boundaries and future ideas

This is cooperative continuity tooling. Files cannot clear conversation context, guarantee lower token usage, authenticate authors or contain a compromised runtime. Signed authorship would require keys and enforcement outside the agent's readable/writable boundary. Isolation, automatic quarantine and incident timelines remain future architecture, not implemented protection.

For current public behavior, read PROTOCOL.md and docs/CLI.md. For live work after adoption, initialize a private `.stigmergy/` directory.
