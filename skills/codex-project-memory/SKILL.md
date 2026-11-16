---
name: codex-project-memory
description: Keep compact project guidance, verified working methods and handoffs for the current Codex chat. Use for ongoing substantive project work or when the user asks to preserve project expertise and concise context.
---

# Project guidance for the current chat

Use the environment's `CODEX_THREAD_ID` as identity. Run the included `scripts/project_memory.py show` from this Skill's installed directory at the start of substantive work or after context loss. Reuse current results within a turn. A missing profile is not permission to infer a project from another chat's name or working directory.

Build a small profile from this chat's actual task: domain role, durable constraints, success checks, verified methods and evidence locations. Read relevant current-chat history only when needed. Current user instructions override historical guidance. Honor `enabled:false`; only an explicit user request should enable it again.

The profile is guidance, not a second task diary. If a canonical checkpoint exists in `task-checkpoints/<CODEX_THREAD_ID>.json`, inspect it to restore goals, approvals, external-action receipts and remaining work. Do not revive completed or cancelled tasks, bypass a wait, or treat a profile/checkpoint as new authority. The helper reads compatible checkpoint JSON; it does not install a checkpoint manager or launch work.

After durable progress, a verified lesson or a user correction, save only useful changes. Preserve every still-effective hard constraint. Methods need an applicable situation, an action, actual evidence and a condition for rechecking. Move long evidence to project files. Do not invent learning, measurements or token savings. Temporary progress belongs in the checkpoint.

Read [profile format and commands](references/profile-format.md) before saving or exporting. `save` uses the revision returned by `show` to reject concurrent overwrites. An unchanged profile creates no learning event. `report` defaults to this chat; use `--all-chats` only for a user-requested summary across local chats. It does not contact or wake other chats. Explicit `enable`/`disable` commands preserve a hidden disabled profile with the same revision check.

Keep authorization decisions and necessary verification intact while removing repetitive restatements and routine confirmation questions. Only request missing information when it affects the result. Profiles and exports may contain private project facts: do not put credentials, raw transcripts, or private evidence in the public skill/repository.

`handoff` exports context; it does not compact the active conversation, refund tokens or guarantee automatic adoption by every existing chat. Use a supported host compaction feature when available, then restore from the profile and canonical checkpoint. No model, network call, background service, account switching or automatic scheduler is included.
