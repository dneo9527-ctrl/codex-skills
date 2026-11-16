# Profile format

Run `python3 scripts/project_memory.py show` from the installed Skill directory, or use its absolute script path. Identity comes only from the current `CODEX_THREAD_ID`. Data are stored under `${CODEX_HOME:-~/.codex}/project-memory`; keep that directory private and outside published source.

Save a JSON object through stdin with the revision from `show` (`null` for a missing profile):

```json
{
  "expected_revision": null,
  "enabled": true,
  "profile": {
    "project": "Example project",
    "role": "Project maintainer",
    "focus": ["Relevant technology"],
    "constraints": ["An actual durable user constraint"],
    "success_checks": ["A meaningful acceptance check"],
    "methods": [],
    "resources": []
  }
}
```

```sh
python3 scripts/project_memory.py save < /path/to/profile-input.json
```

Methods contain exactly `when`, `do`, `evidence`, and `recheck`. Resources contain `path` (absolute evidence path) and `purpose`. Empty arrays are valid; absent evidence is a reason to omit a method. Normal arrays allow six entries; methods/resources allow eight. The packed profile is limited to 4200 Unicode characters, not a measured token count. Oversized input is rejected rather than truncated.

On revision conflict, reload and merge the actual changes. A no-op does not rewrite state. For an explicit user request to disable or re-enable this chat, call `disable` or `enable` with stdin JSON containing only `expected_revision` from `show`. These operations retain the full profile even when disabled `show` hides it. They do not create a missing profile or change collaboration/checkpoint preferences.

```sh
python3 scripts/project_memory.py handoff --out /path/to/new-handoff.json
python3 scripts/project_memory.py report --days 7
```

`handoff` preserves the optional canonical checkpoint and extra action/approval fields, refuses existing output files, and rejects exports over 16000 characters. A compatible checkpoint must be a JSON object with a top-level `thread_id` equal to the current environment ID; filename matching alone is insufficient. It never changes task status. When too large, condense the canonical checkpoint while preserving effective constraints, decisions, receipts, unconfirmed external actions and remaining work.

`report` reads this chat's learning events, includes at most 30 within the selected 1–90 day window, and reports omissions. Add `--all-chats` only for an explicitly requested host-wide summary; it exposes project names and methods from other enabled local profiles. Initialization is setup, not a new technical lesson. Historical revisions may be superseded. No automated weekly job is installed; scheduling requires a separate user request through the host's supported automation tools.

The implementation uses POSIX file locking and private file modes. Python 3.9+ on macOS/Linux is supported by this candidate; native Windows is not implemented. Local data and exported handoffs require their own backup policy.
