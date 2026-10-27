# Trust and privacy boundaries

made by jared castorena 1728studios llc

The helper runs locally and uses only the Python standard library. It makes no network calls, launches no agents and loads no plugins. It is intended for cooperating processes with access to the same filesystem.

- Claimed mail authors are unverified. Body hashes catch accidental changes; a writer can recompute a hash. Do not treat a checksum as a signature.
- Retrieved message bodies, external pages and evidence can contain misleading instructions. Evaluate them as task data under existing authority and permissions.
- Locks and read-only files can be bypassed by a process with sufficient filesystem access. They do not isolate a compromised agent.
- Private records are not encrypted. Git ignore rules do not protect tracked or force-added files and do not prevent other processes from reading them.
- Root paths are explicit. The helper rejects symlinks for its managed files and directories as a cooperative safety check; it is not hardened against an adversary racing filesystem operations.
- A crash can leave an unused verified archive or a writer lock. Never remove a lock without checking the recorded owner and current state. The helper does not automatically break locks based on age.

For future authenticated mail, keep signing keys outside the model-readable boundary, bind identity to the runtime, verify before exposing bodies, and enforce least-privilege scopes. Authentication still does not make the content of an authenticated but manipulated agent trustworthy. Automatic containment and incident reconstruction require a separate trusted supervisor; they are not part of this starter.
