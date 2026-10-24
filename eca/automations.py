"""Scheduled sessions: a TOML file per schedule, one owner loop, one session per run.

Layout (``ECA_AUTOMATIONS_DIR``, default ``~/.ecs/automations``)::

    <id>/automation.toml   source of truth; hand-editable, version controlled if you like
    <id>/state.json        runtime bookkeeping (next run, last run, in flight)
    <id>/memory.md         rolling notes appended after each run
    <id>/runs.jsonl        append-only run log
    .run-jitter-salt       one salt, so a schedule's jitter is stable across restarts

Design notes, and where this deliberately differs from a cloud scheduler:

* **Local time.** Times are interpreted in the machine's local time zone. The
  RRULE keeps a ``TZID`` for compatibility, but no zone database is required.
* **One catch-up run.** A recurring schedule that came due while the app was
  closed runs once at start-up and then jumps to the next future occurrence, so
  a week offline never replays a week of runs. A one-shot runs when it comes due
  and then has no next run at all.
* **Nothing waits for a person.** An unattended run cannot prompt, so each
  automation carries an explicit permission: ``read_only`` (read and web, no
  writes), ``accept_edits`` (file edits, no commands), ``allow_shell`` (both).
  Anything outside that policy is denied to the model, with a reason.
* **Memory is written by the harness**, not by the model: the write tool is
  scoped to the project, so after each run the harness appends the model's own
  closing summary to ``memory.md``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, time as clock, timedelta
from pathlib import Path

WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
FREQUENCIES = ("MINUTELY", "HOURLY", "DAILY", "WEEKLY")
STATUSES = ("ACTIVE", "PAUSED")
PERMISSIONS = ("read_only", "accept_edits", "allow_shell")
NOTIFICATIONS = ("always", "failed_only")
MAX_NAME = 120
MAX_PROMPT = 8000
MAX_MEMORY_APPEND = 1500
MAX_TIMEOUT = 6 * 60 * 60
KIND = "cron"
FIELDS = ("version", "id", "kind", "name", "prompt", "status", "rrule", "permission", "project",
          "model", "reasoning_effort", "notification", "created_at", "updated_at")


# ---------------------------------------------------------------- schedule text

def parse_rrule(text):
    """Parse the RRULE subset this product writes; raise ValueError otherwise."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("rrule is required")
    spec = {"interval": 1, "byhour": None, "byminute": None, "byday": None, "bysecond": None,
            "count": None, "tzid": ""}
    dtstart = None
    rule = None
    for line in text.replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("DTSTART"):
            match = re.match(r"DTSTART(?:;TZID=([^:=]+))?[:=](\d{8}T\d{4,6}Z?)", line, re.I)
            if not match:
                raise ValueError("DTSTART must look like DTSTART;TZID=Area/City:20260101T090000")
            spec["tzid"] = match.group(1) or ""
            stamp = match.group(2).rstrip("Z")
            pattern = "%Y%m%dT%H%M%S" if len(stamp) == 15 else "%Y%m%dT%H%M"
            dtstart = datetime.strptime(stamp, pattern)
        elif line.upper().startswith("RRULE"):
            rule = line[5:].lstrip(":") if line.upper().startswith("RRULE") else line
        else:
            raise ValueError(f"rrule line not understood: {line[:40]} (expected DTSTART and RRULE lines)")
    if rule is None:
        raise ValueError("rrule must contain an RRULE line")
    for part in rule.split(";"):
        if not part:
            continue
        key, _, value = part.partition("=")
        key, value = key.strip().upper(), value.strip()
        if key == "FREQ":
            spec["freq"] = value.upper()
        elif key == "INTERVAL":
            spec["interval"] = max(1, int(value))
        elif key == "BYHOUR":
            spec["byhour"] = _ints(value, 0, 23, "BYHOUR")
        elif key == "BYMINUTE":
            spec["byminute"] = _ints(value, 0, 59, "BYMINUTE")
        elif key == "BYSECOND":
            spec["bysecond"] = _ints(value, 0, 59, "BYSECOND")
        elif key == "BYDAY":
            days = [day.strip().upper() for day in value.split(",") if day.strip()]
            if any(day not in WEEKDAYS for day in days):
                raise ValueError("BYDAY accepts MO,TU,WE,TH,FR,SA,SU")
            spec["byday"] = days
        elif key == "COUNT":
            spec["count"] = max(1, int(value))
        elif key == "UNTIL":
            continue
        else:
            raise ValueError(f"Unsupported RRULE part: {key}")
    if spec.get("freq") not in FREQUENCIES:
        raise ValueError("RRULE FREQ must be one of MINUTELY, HOURLY, DAILY, WEEKLY")
    if spec["freq"] == "MINUTELY" and (spec["byhour"] or spec["byminute"] or spec["byday"]):
        raise ValueError("A MINUTELY schedule cannot also set BYHOUR, BYMINUTE or BYDAY")
    if spec["freq"] == "HOURLY" and (spec["byhour"] or spec["byday"]):
        raise ValueError("An HOURLY schedule cannot also set BYHOUR or BYDAY")
    if spec["freq"] == "DAILY" and spec["byday"]:
        raise ValueError("A DAILY schedule takes no BYDAY; use WEEKLY or omit it")
    if dtstart is None:
        raise ValueError("rrule needs a DTSTART line")
    spec["dtstart"] = dtstart
    return spec


def _ints(value, low, high, label):
    try:
        numbers = [int(part) for part in value.split(",") if part != ""]
    except ValueError:
        raise ValueError(f"{label} must be comma-separated integers") from None
    if not numbers or any(number < low or number > high for number in numbers):
        raise ValueError(f"{label} values must be between {low} and {high}")
    return numbers


def build_rrule(freq, *, interval=1, at="09:00", weekdays=None, start=None, tzid=""):
    """Build the RRULE text this product stores, from simple form fields."""
    freq = str(freq).upper()
    start = start or datetime.now().replace(second=0, microsecond=0)
    lines = [f"DTSTART{';TZID=' + tzid if tzid else ''}:{start.strftime('%Y%m%dT%H%M%S')}"]
    if freq == "ONCE":
        lines.append("RRULE:FREQ=DAILY;COUNT=1")
        return "\n".join(lines)
    if freq not in FREQUENCIES:
        raise ValueError("freq must be ONCE, MINUTELY, HOURLY, DAILY or WEEKLY")
    hour, minute = _clock(at)
    parts = [f"FREQ={freq}"]
    if int(interval) > 1 or freq in ("MINUTELY", "HOURLY"):
        parts.append(f"INTERVAL={max(1, int(interval))}")
    if freq == "HOURLY":
        parts.append(f"BYMINUTE={minute}")
    if freq == "DAILY":
        parts.extend([f"BYHOUR={hour}", f"BYMINUTE={minute}"])
    if freq == "WEEKLY":
        days = [WEEKDAYS[int(day)] for day in (weekdays or [start.weekday()])]
        parts.extend([f"BYDAY={','.join(days)}", f"BYHOUR={hour}", f"BYMINUTE={minute}"])
    lines.append("RRULE:" + ";".join(parts))
    return "\n".join(lines)


def _clock(value):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value or "").strip())
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise ValueError("time must look like 09:30")
    return int(match.group(1)), int(match.group(2))


def describe(spec):
    """Short Chinese summary of a parsed schedule."""
    freq, interval = spec["freq"], spec.get("interval", 1)
    hour = (spec.get("byhour") or [spec["dtstart"].hour])[0]
    minute = (spec.get("byminute") or [spec["dtstart"].minute])[0]
    if spec.get("count") == 1:
        return f"单次 {spec['dtstart']:%Y-%m-%d %H:%M}"
    if freq == "MINUTELY":
        return f"每 {interval} 分钟"
    if freq == "HOURLY":
        return f"每 {interval} 小时（第 {minute} 分）" if interval > 1 else f"每小时第 {minute} 分"
    clock_text = f"{hour:02d}:{minute:02d}"
    if freq == "DAILY":
        return f"每天 {clock_text}" if interval == 1 else f"每 {interval} 天 {clock_text}"
    days = spec.get("byday") or [WEEKDAYS[spec["dtstart"].weekday()]]
    names = {"MO": "一", "TU": "二", "WE": "三", "TH": "四", "FR": "五", "SA": "六", "SU": "日"}
    order = [day for day in WEEKDAYS if day in days]
    label = "、".join(names[day] for day in order)
    if order == list(WEEKDAYS[:5]):
        label = "工作日"
    elif len(order) == 7:
        label = "每天"
    return f"每周{label} {clock_text}" if interval == 1 else f"每 {interval} 周（{label}）{clock_text}"


# ------------------------------------------------------------------- next times

def next_after(spec, after):
    """First occurrence strictly after ``after`` (naive local time), or None."""
    start = spec["dtstart"]
    if spec.get("count") == 1:
        return start if start > after else None
    step = max(1, spec.get("interval", 1))
    freq = spec["freq"]
    if freq == "MINUTELY":
        cursor = start
        if cursor <= after:
            gap = int((after - cursor).total_seconds() // 60) // step + 1
            cursor = start + timedelta(minutes=gap * step)
        return cursor
    hour = (spec.get("byhour") or [start.hour])[0]
    minute = (spec.get("byminute") or [start.minute])[0]
    if freq == "HOURLY":
        cursor = start.replace(minute=minute, second=0, microsecond=0)
        delta = timedelta(hours=step)
        while cursor <= after:
            cursor += delta
        return cursor
    days = spec.get("byday") or ([WEEKDAYS[start.weekday()]] if freq == "WEEKLY" else None)
    day = start.date()
    for _ in range(4000):
        candidate = datetime.combine(day, clock(hour, minute))
        if freq == "WEEKLY":
            week_index = (day - start.date()).days // 7
            in_step = week_index % step == 0
        else:
            in_step = (day - start.date()).days % step == 0
        if in_step and (not days or WEEKDAYS[day.weekday()] in days) and candidate > after:
            return candidate
        day += timedelta(days=1)
    return None


def max_jitter(spec):
    """Jitter window in seconds: spread popular clock times, never one-shots."""
    if spec.get("count") == 1:
        return 0
    freq = spec["freq"]
    if freq == "MINUTELY":
        clean = (spec.get("interval", 1) >= 60 and not spec.get("byminute") and not spec.get("bysecond"))
        return 300 if clean else 0
    if freq not in ("HOURLY", "DAILY", "WEEKLY"):
        return 0
    if len(spec.get("bysecond") or []) > 1:
        return 0
    if len(spec.get("byminute") or []) > 1:
        return 119
    return 300


def jitter(automation_id, nominal_ms, salt, window):
    """Deterministic offset in [-window, +window] seconds for one nominal time."""
    if window <= 0:
        return 0
    digest = hashlib.sha256(f"{salt}:{automation_id}:{nominal_ms}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % (2 * window + 1) - window


def next_run(automation, now_ms, salt, after_nominal_ms=None):
    """Next (jittered) run time, plus the nominal one for display."""
    spec = parse_rrule(automation["rrule"])
    reference = max(now_ms, after_nominal_ms or now_ms)
    nominal = next_after(spec, datetime.fromtimestamp(reference / 1000))
    if nominal is None:
        return None
    nominal_ms = int(nominal.timestamp() * 1000)
    offset = jitter(automation["id"], nominal_ms, salt, max_jitter(spec)) * 1000
    return {"next_run_at": max(now_ms, nominal_ms + offset), "next_run_nominal_at": nominal_ms}


# ------------------------------------------------------------------------ files

def home():
    override = os.environ.get("ECA_AUTOMATIONS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".ecs" / "automations"


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def dump(automation):
    """Serialise to the same hand-editable TOML shape Codex automations use."""
    lines = []
    for field in FIELDS:
        value = automation.get(field)
        if value in (None, ""):
            continue
        lines.append(f"{field} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def clean(fields, *, existing=None):
    """Validate submitted fields; return the record that will be written."""
    merged = dict(existing or {})
    merged.update({key: value for key, value in (fields or {}).items() if key in FIELDS})
    name = str(merged.get("name") or "").strip()
    if not name or len(name) > MAX_NAME:
        raise ValueError(f"name is required and must be at most {MAX_NAME} characters")
    prompt = str(merged.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required: it is what the scheduled session is asked to do")
    if len(prompt) > MAX_PROMPT:
        raise ValueError(f"prompt is longer than {MAX_PROMPT} characters; link a file instead")
    project = str(merged.get("project") or "").strip()
    if not project:
        raise ValueError("project is required")
    if not Path(project).is_dir():
        raise ValueError(f"project directory does not exist: {project}")
    permission = str(merged.get("permission") or "read_only")
    if permission not in PERMISSIONS:
        raise ValueError(f"permission must be one of {', '.join(PERMISSIONS)}")
    status = str(merged.get("status") or "ACTIVE").upper()
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    notification = str(merged.get("notification") or "always")
    if notification not in NOTIFICATIONS:
        raise ValueError(f"notification must be one of {', '.join(NOTIFICATIONS)}")
    parse_rrule(merged.get("rrule"))
    now = int(time.time() * 1000)
    record = {
        "version": 1,
        "id": merged.get("id") or uuid.uuid4().hex[:12],
        "kind": KIND,
        "name": name,
        "prompt": prompt,
        "status": status,
        "rrule": merged["rrule"].strip(),
        "permission": permission,
        "project": str(Path(project).resolve()),
        "notification": notification,
        "created_at": int(merged.get("created_at") or now),
        "updated_at": now,
    }
    for optional in ("model", "reasoning_effort"):
        value = str(merged.get(optional) or "").strip()
        if value:
            record[optional] = value
    return record


class Library:
    """Reads and writes the on-disk automation library."""

    def __init__(self, directory=None):
        self.dir = Path(directory) if directory else home()
        self._salt = None

    def _ensure(self):
        self.dir.mkdir(parents=True, exist_ok=True)

    def folder(self, automation_id):
        return self.dir / str(automation_id)

    def salt(self):
        if self._salt:
            return self._salt
        self._ensure()
        path = self.dir / ".run-jitter-salt"
        try:
            value = path.read_text("utf-8").strip()
        except OSError:
            value = ""
        if not value:
            value = uuid.uuid4().hex
            try:
                path.write_text(value + "\n", "utf-8")
            except OSError:
                pass
        self._salt = value
        return value

    def ids(self):
        if not self.dir.is_dir():
            return []
        return sorted(entry.name for entry in self.dir.iterdir()
                      if entry.is_dir() and (entry / "automation.toml").is_file())

    def load(self, automation_id):
        import tomllib
        path = self.folder(automation_id) / "automation.toml"
        try:
            data = tomllib.loads(path.read_text("utf-8"))
        except OSError:
            raise ValueError(f"Automation not found: {automation_id}") from None
        data["id"] = str(data.get("id") or automation_id)
        data.update(self.state(automation_id))
        return data

    def list(self):
        rows = []
        for automation_id in self.ids():
            try:
                rows.append(self.view(self.load(automation_id)))
            except (ValueError, OSError):
                continue
        rows.sort(key=lambda row: (row.get("next_run_at") or 0, row["name"]))
        return rows

    def view(self, automation):
        try:
            label = describe(parse_rrule(automation["rrule"]))
        except ValueError:
            label = "计划无效"
        return {**automation, "schedule": label}

    def save(self, fields):
        self._ensure()
        automation_id = str((fields or {}).get("id") or "").strip()
        existing = None
        if automation_id:
            try:
                existing = self.load(automation_id)
            except ValueError:
                existing = None
        record = clean(fields, existing=existing)
        folder = self.folder(record["id"])
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "automation.toml"
        temporary = folder / "automation.toml.tmp"
        temporary.write_text(dump(record), "utf-8")
        temporary.replace(target)
        state = self.state(record["id"])
        if record["status"] != "ACTIVE":
            state.update({"next_run_at": None, "next_run_nominal_at": None})
        elif state.get("last_run_at") is None and state.get("next_run_at") is None:
            planned = next_run(record, int(time.time() * 1000), self.salt())
            if planned:
                state.update(planned)
        self.write_state(record["id"], state)
        return self.view(self.load(record["id"]))

    def delete(self, automation_id):
        import shutil
        folder = self.folder(automation_id)
        if not folder.is_dir():
            raise ValueError(f"Automation not found: {automation_id}")
        shutil.rmtree(folder)
        return True

    def state(self, automation_id):
        path = self.folder(automation_id) / "state.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        return {
            "next_run_at": data.get("next_run_at"),
            "next_run_nominal_at": data.get("next_run_nominal_at"),
            "last_run_at": data.get("last_run_at"),
            "last_status": data.get("last_status"),
            "last_error": data.get("last_error"),
            "last_session": data.get("last_session"),
        }

    def write_state(self, automation_id, state):
        folder = self.folder(automation_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "state.json"
        temporary = folder / "state.json.tmp"
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
        temporary.replace(path)

    def patch_state(self, automation_id, **changes):
        state = self.state(automation_id)
        state.update(changes)
        self.write_state(automation_id, state)
        return state

    def history(self, automation_id, limit=20):
        path = self.folder(automation_id) / "runs.jsonl"
        rows = []
        try:
            for line in path.read_text("utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        except OSError:
            return []
        return rows[-limit:][::-1]

    def append_run(self, automation_id, record):
        folder = self.folder(automation_id)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "runs.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def memory(self, automation_id, limit=8000):
        try:
            return (self.folder(automation_id) / "memory.md").read_text("utf-8")[-limit:]
        except OSError:
            return ""

    def append_memory(self, automation_id, text):
        text = (text or "").strip()
        if not text:
            return
        folder = self.folder(automation_id)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with (folder / "memory.md").open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {stamp}\n{text[:MAX_MEMORY_APPEND]}\n")


def migration_note(state):
    """A run left 'running' by a crash is not silently counted as success."""
    if state.get("last_status") == "running":
        return "interrupted"
    return None


PERMISSION_TEXT = {
    "read_only": "只读（可读文件、可联网，不改文件、不跑命令）",
    "accept_edits": "可改文件（不能跑命令）",
    "allow_shell": "可改文件并可跑命令",
}


def _approver(permission, emit):
    """Unattended runs cannot wait for a person; anything outside policy is denied."""
    async def approve(message, detail=None):
        text = str(message or "").lower()
        if permission == "allow_shell":
            return True
        if "web" in text or "联网" in text:
            return True
        try:
            emit("notice", "定时任务按权限拒绝了需要人工批准的操作：" + str(message)[:160])
        except Exception:
            pass
        return False
    return approve


def _last_text(state, limit=1500):
    for message in reversed(state.get("messages") or []):
        if message.get("role") == "assistant":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()[:limit]
    return ""


def _memory_text(record):
    body = record.get("summary") or record.get("error") or ""
    head = f"状态：{record.get('status')}（{record.get('trigger')}）"
    if record.get("session_id"):
        head += f" · 会话 {str(record['session_id'])[:8]}"
    return head + ("\n" + body if body else "")


class Runner:
    """Runs one automation as a real session in its project."""

    def __init__(self, library, emit=None, timeout=MAX_TIMEOUT):
        self.library = library
        self.emit = emit or (lambda *_: None)
        self.timeout = timeout

    def prompt(self, automation):
        memory = self.library.memory(automation["id"])
        last = automation.get("last_run_at")
        last_text = datetime.fromtimestamp(last / 1000).strftime("%Y-%m-%d %H:%M") if last else "从未"
        lines = [
            f"定时任务：{automation['name']}",
            f"Automation ID: {automation['id']}",
            f"本次运行时间：{datetime.now():%Y-%m-%d %H:%M}",
            f"上次运行：{last_text}",
            f"权限：{PERMISSION_TEXT.get(automation.get('permission'), automation.get('permission'))}",
            "本次运行无人值守：需要人批准的操作会被拒绝，请在这个权限范围内完成。",
            "结束前用 3-6 行写清本轮结论：做了什么、发现了什么、下次运行该注意什么。"
            "这段结论会被自动追加到该任务的记忆文件，成为下一轮的上下文。",
        ]
        if memory.strip():
            lines.append("历史记忆（参考用，别重复已经完成的结论）：\n" + memory[-3000:])
        lines.append("任务说明：\n" + automation["prompt"])
        return "\n\n".join(lines)

    async def __call__(self, automation, *, trigger="scheduled"):
        from dataclasses import replace
        from .agent import Agent
        from .config import Settings
        from .store import Store

        started = int(time.time() * 1000)
        record = {"started_at": started, "trigger": trigger, "status": "running",
                  "session_id": None, "stop_reason": None, "error": None, "summary": ""}
        store = None
        try:
            root = Path(automation["project"])
            if not root.is_dir():
                raise ValueError(f"项目目录不存在：{root}")
            # Settings.load picks the app's model connection up from the environment,
            # so a scheduled run uses the model configured right now.
            settings = Settings.load(root)
            permission = automation.get("permission") or "read_only"
            mode = "research" if permission == "read_only" else "code"
            settings = replace(settings, mode=mode,
                               permission="accept-edits" if permission != "read_only" else settings.permission)
            if automation.get("model"):
                settings = replace(settings, model=automation["model"])
            if automation.get("reasoning_effort"):
                settings = replace(settings, reasoning_effort=automation["reasoning_effort"])
            settings.validate()
            # The app may already hold this project; a scheduled run joins it
            # instead of failing the way a second process would.
            store = Store(root, shared=True)
            state = store.create(mode=mode)
            state["title"] = (automation.get("name") or "定时任务")[:60]
            state["automation_id"] = automation["id"]
            state["automation_trigger"] = trigger
            store.save(state)
            record["session_id"] = state["id"]

            async def question(message):
                return ""

            agent = Agent(settings, store, state, _approver(permission, self.emit), question, self.emit)
            try:
                await asyncio.wait_for(agent.run(self.prompt(automation)), timeout=self.timeout)
            except asyncio.TimeoutError:
                raise ValueError(f"运行超过 {self.timeout} 秒，已中止") from None
            status = state.get("status")
            record["status"] = "succeeded" if status == "idle" else (status or "unknown")
            record["stop_reason"] = state.get("stop_reason")
            record["summary"] = _last_text(state)
        except Exception as exc:  # a failed run is data, not a crash of the scheduler
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"[:600]
        finally:
            record["finished_at"] = int(time.time() * 1000)
            if record["status"] == "running":
                record["status"] = "failed"
                record["error"] = record.get("error") or "运行没有正常结束"
            try:
                self.library.append_run(automation["id"], record)
                self.library.append_memory(automation["id"], _memory_text(record))
                self.library.patch_state(automation["id"], last_run_at=record["started_at"],
                                         last_status=record["status"], last_error=record["error"],
                                         last_session=record["session_id"])
            except OSError:
                pass
            if store is not None:
                try:
                    store.close()
                except Exception:
                    pass
            try:
                self.emit("automation_run", {**record, "automation_id": automation["id"],
                                             "name": automation.get("name"),
                                             "notification": automation.get("notification") or "always"})
            except Exception:
                pass
        return record


class Scheduler:
    """The single owner loop: due schedules become sessions, one at a time each."""

    TICK_SECONDS = 30.0
    MAX_PER_TICK = 3
    MIN_GAP_MS = 60_000

    def __init__(self, library=None, runner=None, emit=None, *, tick_seconds=None, clock=time.time):
        self.library = library or Library()
        self.runner = runner or Runner(self.library, emit)
        self.emit = emit or (lambda *_: None)
        self.tick_seconds = tick_seconds or self.TICK_SECONDS
        self.clock = clock
        self._loop_task = None
        self._inflight = set()
        self._tasks = set()
        self._stopped = False

    def start(self):
        if self._loop_task is None:
            self._stopped = False
            self._loop_task = asyncio.create_task(self._loop())
        return self

    async def stop(self):
        self._stopped = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):
                pass
            self._loop_task = None

    async def _loop(self):
        try:
            self._settle()
        except Exception:
            pass
        try:
            await self.tick()
        except Exception as exc:
            self.emit("notice", f"定时任务首次检查失败：{exc}")
        while not self._stopped:
            await asyncio.sleep(self.tick_seconds)
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.emit("notice", f"定时任务检查失败：{exc}")

    def _settle(self):
        """A run left 'running' by a crash is recorded as interrupted, not success."""
        for automation_id in self.library.ids():
            state = self.library.state(automation_id)
            if migration_note(state) is None:
                continue
            self.library.append_run(automation_id, {
                "started_at": state.get("last_run_at"), "finished_at": int(self.clock() * 1000),
                "trigger": "scheduled", "status": "interrupted", "session_id": state.get("last_session"),
                "stop_reason": None, "error": "应用在这次运行中被关闭", "summary": ""})
            self.library.patch_state(automation_id, last_status="interrupted")

    def due(self, now=None):
        now = now if now is not None else int(self.clock() * 1000)
        rows = []
        for row in self.library.list():
            if row.get("status") != "ACTIVE" or not row.get("next_run_at"):
                continue
            if row["next_run_at"] > now:
                continue
            if row["id"] in self._inflight:
                continue
            last = row.get("last_run_at")
            if last and last + self.MIN_GAP_MS > now:
                continue
            rows.append(row)
        return rows

    def plan(self, automation, now):
        """Advance the schedule: one catch-up run, then the next future occurrence."""
        overdue = (automation.get("next_run_at") or 0) <= now
        planned = next_run(automation, now, self.library.salt(),
                           after_nominal_ms=automation.get("next_run_nominal_at") if overdue else None)
        if planned is None:
            self.library.patch_state(automation["id"], next_run_at=None, next_run_nominal_at=None)
        else:
            self.library.patch_state(automation["id"], **planned)
        self.emit("automations", self.library.list())
        return planned

    async def tick(self):
        now = int(self.clock() * 1000)
        rows = self.due(now)[:self.MAX_PER_TICK]
        for row in rows:
            self.plan(row, now)
            self._inflight.add(row["id"])
            task = asyncio.create_task(self._run(row))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return len(rows)

    async def _run(self, automation):
        try:
            return await self.runner(automation, trigger="scheduled")
        except Exception as exc:
            self.emit("notice", f"定时任务 {automation.get('name')} 运行失败：{exc}")
            return None
        finally:
            self._inflight.discard(automation["id"])
            self.emit("automations", self.library.list())

    async def run_now(self, automation_id):
        """Manual run: never overlaps a scheduled one, never disturbs the timing."""
        automation = self.library.load(automation_id)
        if automation_id in self._inflight:
            raise ValueError("这个任务正在运行，等它结束再试")
        if automation.get("status") != "ACTIVE":
            self.library.save({"id": automation_id, "status": "ACTIVE"})
            automation = self.library.load(automation_id)
        now = int(self.clock() * 1000)
        if (automation.get("next_run_at") or 0) <= now:
            self.plan(automation, now)
        self._inflight.add(automation_id)
        try:
            return await self.runner(automation, trigger="manual")
        finally:
            self._inflight.discard(automation_id)
            self.emit("automations", self.library.list())


def enabled():
    """Schedules run only when a host asked for it.

    The desktop sets ECA_AUTOMATIONS_DIR when it starts the backend. Without it
    (tests, one-shot CLI runs) nothing starts on its own, so a test suite can
    never fire a user's real schedules.
    """
    return bool(os.environ.get("ECA_AUTOMATIONS_DIR"))
