#!/usr/bin/env python3
"""Bounded per-chat project guidance and learning events. No model or network."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from datetime import datetime, timezone

ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def valid_text(value, key, limit=600):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("invalid text: " + key)


def validate_profile(profile):
    fields = {"project", "role", "focus", "constraints", "success_checks", "methods", "resources"}
    if not isinstance(profile, dict) or set(profile) != fields:
        raise ValueError("profile requires exactly: " + ", ".join(sorted(fields)))
    valid_text(profile["project"], "project", 240)
    valid_text(profile["role"], "role", 300)
    for key in fields - {"project", "role"}:
        limit = 8 if key in ("methods", "resources") else 6
        if not isinstance(profile[key], list) or len(profile[key]) > limit:
            raise ValueError("invalid/too many entries: " + key)
        for item in profile[key]:
            if key in ("methods", "resources"):
                expected = {"when", "do", "evidence", "recheck"} if key == "methods" else {"path", "purpose"}
                if not isinstance(item, dict) or set(item) != expected:
                    raise ValueError("invalid fields in " + key)
                for field, value in item.items():
                    valid_text(value, key + "." + field, 1000 if field == "path" else 600)
                if key == "resources" and not Path(item["path"]).is_absolute():
                    raise ValueError("resource path must be absolute")
            else:
                valid_text(item, key)
    if len(packed(profile)) > 4200:
        raise ValueError("profile exceeds 4200 characters; move details into project evidence")
    return profile


def revision(enabled, profile):
    return hashlib.sha256(packed({"enabled": enabled, "profile": profile}).encode()).hexdigest()


def load(path):
    if path.is_symlink():
        raise ValueError("refusing symlink: " + str(path))
    if not path.exists():
        return None
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("file exceeds read budget: " + str(path))
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("expected JSON object: " + str(path))
    return result


def read_profile(path, thread):
    data = load(path)
    if data is None:
        return None
    if data.get("thread_id") != thread or data.get("schema_version") != 1:
        raise ValueError("profile identity/schema mismatch")
    if type(data.get("enabled")) is not bool:
        raise ValueError("enabled must be boolean")
    validate_profile(data.get("profile"))
    if data.get("revision") != revision(data["enabled"], data["profile"]):
        raise ValueError("profile revision mismatch")
    return data


def atomic_write(path, data):
    if path.is_symlink():
        raise ValueError("refusing symlink destination")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temp = file.name
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def checkpoint(path, thread):
    cp = load(path)
    if cp is not None and cp.get("thread_id") != thread:
        raise ValueError("checkpoint identity mismatch")
    return cp


def brief(path, cp):
    if cp is None:
        return {"found": False, "path": str(path)}
    result = {"found": True, "path": str(path), "details_required": True}
    for key in ("status", "updated_at", "waiting_for_user", "needs_approval", "auto_resumable"):
        result[key] = cp.get(key)
    context = {k: cp[k] for k in ("goal", "constraints", "remaining", "next_action", "blockers") if k in cp}
    if len(packed(context)) <= 2300:
        result["brief"] = context
    else:
        result["brief_omitted"] = "read canonical checkpoint; no constraints truncated"
    return result


def save(path, thread, request):
    if not isinstance(request, dict) or set(request) != {"expected_revision", "enabled", "profile"}:
        raise ValueError("save requires expected_revision, enabled and profile only")
    if type(request["enabled"]) is not bool:
        raise ValueError("enabled must be boolean")
    profile = validate_profile(request["profile"])
    expected = request["expected_revision"]
    if expected is not None and (not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected)):
        raise ValueError("invalid expected_revision")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path.with_suffix(".lock")), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = read_profile(path, thread)
        if expected != (current["revision"] if current else None):
            raise ValueError("revision conflict: show current profile and merge")
        rev = revision(request["enabled"], profile)
        if current and current["revision"] == rev:
            return {"saved": False, "reason": "unchanged", "revision": rev}
        now = datetime.now(timezone.utc).isoformat()
        data = {"schema_version": 1, "thread_id": thread, "enabled": request["enabled"],
                "revision": rev, "updated_at": now, "profile": profile}
        old_profile = current["profile"] if current else {}
        event = {"schema_version": 1, "thread_id": thread, "at": now, "revision": rev,
                 "project": profile["project"], "kind": "update" if current else "initialization",
                 "changed_fields": [k for k in profile if profile[k] != old_profile.get(k)],
                 "methods_added": [m for m in profile["methods"] if m not in old_profile.get("methods", [])],
                 "methods_removed": [m for m in old_profile.get("methods", []) if m not in profile["methods"]]}
        learning_root = path.parent / "learning"
        learning_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        learning_root.chmod(0o700)
        event_path = learning_root / thread / (str(time.time_ns()) + "-" + rev[:12] + ".json")
        # Record events only after a profile commit. A crash can omit a learning
        # record, but cannot report an uncommitted suggestion as accepted work.
        event["previous_revision"] = current["revision"] if current else None
        event_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        event_path.parent.chmod(0o700)
        atomic_write(path, data)
        atomic_write(event_path, event)
        return {"saved": True, "path": str(path), "revision": rev,
                "profile_characters": len(packed(profile)), "learning_event": str(event_path)}


def report(base, days, thread=None):
    cutoff = time.time() - days * 86400
    events = []
    invalid = 0
    pattern = thread + "/*.json" if thread is not None else "*/*.json"
    for path in (base / "project-memory" / "learning").glob(pattern):
        try:
            event = load(path)
            if not event or not ID_RE.fullmatch(event.get("thread_id", "")) or path.parent.name != event["thread_id"]:
                raise ValueError("invalid event identity")
            at = datetime.fromisoformat(event["at"]).timestamp()
            if not cutoff <= at <= time.time() + 60:
                continue
            current = read_profile(base / "project-memory" / (event["thread_id"] + ".json"), event["thread_id"])
            if not current or not current["enabled"]:
                continue
            # Only a currently committed revision is authoritative. Earlier
            # events remain available via paths but are explicitly historical.
            event["current_revision"] = current["revision"] == event["revision"]
            event["event_path"] = str(path)
            events.append(event)
        except (OSError, ValueError, KeyError, TypeError):
            invalid += 1
    events.sort(key=lambda e: e["at"], reverse=True)
    selected = []
    chars = 0
    for event in events[:30]:
        if chars + len(packed(event)) > 18000:
            break
        selected.append(event)
        chars += len(packed(event))
    return {"days": days, "scope": "current_chat" if thread is not None else "all_local_chats",
            "event_count": len(events), "events": selected,
            "omitted_count": len(events) - len(selected), "invalid_records": invalid,
            "note": "initialization is setup, not new expertise; historical rules may be superseded; no token savings measured"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("show", "save", "enable", "disable", "handoff", "report"))
    parser.add_argument("--out", type=Path, help="absolute new handoff file")
    parser.add_argument("--days", type=int, default=7, help="report lookback, 1 to 90")
    parser.add_argument("--all-chats", action="store_true", help="report only: explicitly include all local chat learning events")
    args = parser.parse_args()
    try:
        base = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().absolute()
        thread = os.environ.get("CODEX_THREAD_ID", "")
        if args.all_chats and args.action != "report":
            raise ValueError("--all-chats only applies to report")
        if args.action == "report":
            if args.out or not 1 <= args.days <= 90:
                raise ValueError("report accepts --days 1..90, no --out")
            if not args.all_chats and not ID_RE.fullmatch(thread):
                raise ValueError("valid CODEX_THREAD_ID required for current-chat report")
            result = report(base, args.days, None if args.all_chats else thread)
        else:
            if not ID_RE.fullmatch(thread):
                raise ValueError("valid CODEX_THREAD_ID required; do not infer identity")
            path = base / "project-memory" / (thread + ".json")
            cp_path = base / "task-checkpoints" / (thread + ".json")
            if args.action in ("save", "enable", "disable"):
                if args.out:
                    raise ValueError("--out only applies to handoff")
                raw = sys.stdin.read(65537)
                if len(raw) > 65536:
                    raise ValueError("input exceeds 64K characters")
                request = json.loads(raw)
                if args.action != "save":
                    if not isinstance(request, dict) or set(request) != {"expected_revision"}:
                        raise ValueError("enable/disable requires expected_revision only")
                    current = read_profile(path, thread)
                    if current is None:
                        raise ValueError("profile missing; save a real project profile first")
                    request = {"expected_revision": request["expected_revision"],
                               "enabled": args.action == "enable", "profile": current["profile"]}
                result = save(path, thread, request)
            else:
                profile = read_profile(path, thread)
                if args.action == "show" and args.out:
                    raise ValueError("--out only applies to handoff")
                result = {"found": profile is not None, "thread_id": thread, "path": str(path),
                          "revision": profile["revision"] if profile else None,
                          "enabled": profile["enabled"] if profile else True}
                if profile and not profile["enabled"]:
                    result["reason"] = "disabled_for_this_chat"
                else:
                    cp = checkpoint(cp_path, thread)
                    if profile:
                        result["profile"] = profile["profile"]
                    if args.action == "show":
                        result["checkpoint"] = brief(cp_path, cp)
                    else:
                        if args.out is None or not args.out.is_absolute():
                            raise ValueError("handoff requires --out /absolute/new/file.json")
                        if args.out.absolute() in (path, cp_path):
                            raise ValueError("cannot replace canonical state")
                        result.update(checkpoint=cp, checkpoint_path=str(cp_path), context_compacted=False,
                                      authority="historical context; no new permission")
                        if len(packed(result)) > 16000:
                            raise ValueError("handoff exceeds 16000 characters; condense canonical checkpoint, preserve constraints/actions")
                        args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        fd = os.open(str(args.out), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        with os.fdopen(fd, "w", encoding="utf-8") as file:
                            file.write(packed(result) + "\n")
                            file.flush()
                            os.fsync(file.fileno())
                        result = {"exported": str(args.out), "context_compacted": False, "characters": len(packed(result))}
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
