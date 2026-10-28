"""Opportunity scanning: find payable products a small team could rebuild.

Where the business mode judges one direction, this one is a sweep: read many
public pages about mature small and mid-sized companies, list at least twenty
products a small team could actually rebuild, and then cut it down.

The gates exist because a model asked for "ideas" returns the same top-of-mind
list every time. Here that is refused by construction:

* at most three candidates per category, so twenty ideas cannot be twenty SaaS
  dashboards;
* a shortlist only exists once twenty candidates span at least eight categories
  and an explicit rejection list of at least five obvious ideas is on disk;
* every candidate needs a registered page, a price, a named buyer, a reason a
  small team can build it, the way it most likely fails, and why it is *not*
  the obvious pick.

Everything lives under ``<project>/.eca/scout`` so the folder, not the chat, is
the deliverable.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

STAGES = ("criteria", "sweep", "screen", "shortlist")
LABELS = {"criteria": "立标准", "sweep": "扫样本", "screen": "筛与排除", "shortlist": "候选清单"}
EFFORT = ("days", "weeks", "months")
SOURCE_KINDS = ("product", "pricing", "marketplace", "review", "community", "report", "other")
MAX_PER_CATEGORY = 3
MIN_CANDIDATES = 20
MIN_CANDIDATES_EARLY = 12
MIN_CATEGORIES = 8
MIN_EXCLUDED = 5
SHORTLIST_RANGE = (3, 7)
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_FILE = 2_000_000
MAX_TEXT = 4000

REQUIRES = {
    "criteria": (),
    "sweep": ("criteria",),
    "screen": ("half",),
    "shortlist": ("candidates", "categories", "excluded"),
}
NEEDS = {
    "criteria": "write .eca/scout/criteria.md with scout_doc first: what counts as replicable by a small "
                "team, what you refuse to consider, and the budget/时间 boundary",
    "half": f"register at least {MIN_CANDIDATES_EARLY} candidates with scout_candidate before screening; "
            "breadth first, judgement later",
    "candidates": f"register at least {MIN_CANDIDATES} candidates with scout_candidate",
    "categories": f"spread candidates over at least {MIN_CATEGORIES} categories (at most {MAX_PER_CATEGORY} per "
                  "category). Twenty variants of the same dashboard is the failure mode this mode exists for",
    "excluded": f"write at least {MIN_EXCLUDED} rejected ideas with scout_exclude (name the obvious ones and say "
                "why they are not worth it)",
}

DOCUMENTS = ("criteria.md", "notes.md")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def base(root):
    return Path(root) / ".eca" / "scout"


def _read(path, limit=MAX_FILE):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return ""
        return path.read_text("utf-8", errors="replace")
    except OSError:
        return ""


def _jsonl(path):
    rows = []
    for line in _read(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _save(path, text, append=False):
    """Write one artifact; a full or read-only disk is named, not dumped raw."""
    from . import fsguard
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(text)
        else:
            path.write_text(text, "utf-8")
        return path.stat().st_size
    except OSError as error:
        raise ValueError(fsguard.describe(error, "写入选品制品", path)) from None


def _write_jsonl(path, rows):
    _save(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def _clean_id(value, label="id"):
    if not isinstance(value, str) or not ID_PATTERN.match(value.strip().lower()):
        raise ValueError(f"{label} must be lowercase letters, digits, '.', '_' or '-' (max 64)")
    return value.strip().lower()


def _text(value, label, limit=MAX_TEXT, allow_empty=False):
    if value is None and allow_empty:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    value = value.strip()
    if not value and not allow_empty:
        raise ValueError(f"{label} cannot be empty")
    if len(value) > limit:
        raise ValueError(f"{label} is limited to {limit} characters")
    return value


def _list(value, label, most=16, limit=600, least=1):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    rows = [_text(item, label, limit) for item in value]
    if len(rows) < least:
        raise ValueError(f"{label} needs at least {least} entr" + ("y" if least == 1 else "ies"))
    if len(rows) > most:
        raise ValueError(f"{label} is limited to {most} entries")
    return rows


def stage_list():
    return [{"id": key, "label": LABELS[key]} for key in STAGES]


def clean(state):
    state = state if isinstance(state, dict) else {}
    stage = state.get("stage") if state.get("stage") in STAGES else STAGES[0]
    history = []
    for entry in state.get("history") or []:
        if not isinstance(entry, dict):
            continue
        history.append({"from": entry.get("from") if entry.get("from") in STAGES else None,
                        "to": entry.get("to") if entry.get("to") in STAGES else None,
                        "at": str(entry.get("at") or ""), "note": str(entry.get("note") or "")[:500]})
    return {"stage": stage, "history": history[-40:], "topic": str(state.get("topic") or "")[:300]}


def _tally(rows):
    tally = {}
    for row in rows:
        key = str(row.get("category") or "").strip().lower()
        tally[key] = tally.get(key, 0) + 1
    return tally


def present(root):
    """Which artifacts exist and how the spread looks, so a gate can name the gap."""
    folder = base(root)
    sources = _jsonl(folder / "sources.jsonl")
    candidates = _jsonl(folder / "candidates.jsonl")
    excluded = _jsonl(folder / "excluded.jsonl")
    tally = _tally(candidates)
    categories = {key for key in tally if key}
    return {
        "criteria": bool(_read(folder / "criteria.md").strip()),
        "half": len(candidates) >= MIN_CANDIDATES_EARLY,
        "candidates": len(candidates) >= MIN_CANDIDATES,
        "categories": len(categories) >= MIN_CATEGORIES,
        "excluded": len(excluded) >= MIN_EXCLUDED,
        "shortlist": bool(_read(folder / "shortlist.md").strip()),
        "sources_rows": sources, "candidates_rows": candidates, "excluded_rows": excluded,
        "tally": tally, "categories_found": sorted(categories),
    }


def counts(root):
    found = present(root)
    return {"sources": len(found["sources_rows"]), "candidates": len(found["candidates_rows"]),
            "categories": len(found["categories_found"]), "excluded": len(found["excluded_rows"]),
            "shortlist": found["shortlist"]}


def artifacts(root):
    folder = base(root)
    if not folder.is_dir():
        return []
    items = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            items.append({"name": path.relative_to(folder).as_posix(), "bytes": path.stat().st_size})
        except OSError:
            continue
        if len(items) >= 200:
            break
    return items


def public(state, root):
    state = clean(state)
    found = present(root)
    picks = []
    raw = _read(base(root) / "shortlist.json")
    if raw.strip():
        try:
            picks = json.loads(raw).get("picks") or []
        except (ValueError, AttributeError):
            picks = []
    return {"stage": state["stage"], "label": LABELS[state["stage"]], "stages": stage_list(),
            "history": state["history"], "counts": counts(root), "artifacts": artifacts(root),
            "tally": found["tally"], "picks": picks}


def missing(root, target):
    found = present(root)
    return [key for key in REQUIRES[target] if not found[key]]


def enter(root, state, target, note=""):
    if target not in STAGES:
        raise ValueError(f"stage must be one of: {', '.join(STAGES)}")
    state = clean(state)
    current, wanted = STAGES.index(state["stage"]), STAGES.index(target)
    if wanted == current:
        return state
    note = _text(note, "note", 500, allow_empty=True)
    if wanted < current and not note:
        raise ValueError(f"Moving back from {state['stage']} to {target} changes what the earlier list means, "
                         "so pass a note explaining why (a category was over-represented, an excluded idea "
                         "turned out to be payable).")
    absent = missing(root, target)
    if absent:
        raise ValueError(f"Cannot enter {target}: {', '.join(absent)} missing. "
                         + " ".join(NEEDS[key] for key in absent))
    state["history"].append({"from": state["stage"], "to": target, "at": now(), "note": note})
    state["stage"] = target
    _save(base(root) / "stage.json", json.dumps(
        {"stage": target, "updated_at": now(), "history": state["history"][-40:]},
        ensure_ascii=False, indent=2))
    return state


def add_source(root, source):
    ident = _clean_id(source.get("id"), "source id")
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(SOURCE_KINDS)}")
    url = _text(source.get("url"), "url", 2000)
    if not url.startswith("https://"):
        raise ValueError("source url must be https")
    row = {"id": ident, "kind": kind, "url": url,
           "title": _text(source.get("title"), "title", 400),
           "published": _text(source.get("published"), "published", 40, allow_empty=True),
           "registered_at": now(),
           "note": _text(source.get("note"), "note", 600, allow_empty=True)}
    path = base(root) / "sources.jsonl"
    rows = [old for old in _jsonl(path) if old.get("id") != ident]
    rows.append(row)
    _write_jsonl(path, rows)
    return row


def write_doc(root, name, content, append=False):
    if not isinstance(name, str):
        raise ValueError("name must be text")
    name = name.strip().replace("\\", "/").lstrip("./")
    if name not in DOCUMENTS:
        raise ValueError("name must be one of: " + ", ".join(DOCUMENTS)
                         + "; candidates, the rejection list and the shortlist are written by their own tools")
    body = _text(content, "content", 200_000, allow_empty=True)
    if append and not body.endswith("\n"):
        body += "\n"
    size = _save(base(root) / name, body, append)
    return {"name": name, "bytes": size, "appended": append}


def add_candidate(root, data):
    """One payable product a small team could rebuild, with the spread quota enforced."""
    ident = _clean_id(data.get("id"), "candidate id")
    category = _text(data.get("category"), "category", 60).strip().lower()
    known = {row.get("id") for row in _jsonl(base(root) / "sources.jsonl")}
    sources = [str(value).strip().lower() for value in (data.get("sources") or [])]
    unknown = [value for value in sources if value not in known]
    if unknown:
        raise ValueError("Unknown source id(s) " + ", ".join(unknown)
                         + ": register the product page with scout_source first, so a candidate cannot cite a "
                           "page nobody opened.")
    if not sources:
        raise ValueError("A candidate needs at least one registered source (the product or pricing page).")
    effort = data.get("effort")
    if effort not in EFFORT:
        raise ValueError("effort must be one of: " + ", ".join(EFFORT))
    path = base(root) / "candidates.jsonl"
    rows = _jsonl(path)
    tally = _tally([row for row in rows if row.get("id") != ident])
    if tally.get(category, 0) >= MAX_PER_CATEGORY:
        crowded = ", ".join(f"{key} {value}" for key, value in sorted(tally.items()))
        raise ValueError(f"Category '{category}' already has {MAX_PER_CATEGORY} candidates ({crowded}). "
                         "This mode exists to leave the obvious pool: look in another industry, another buyer "
                         "or another delivery form instead of a fourth variant of the same thing.")
    row = {"id": ident, "name": _text(data.get("name"), "name", 200),
           "company": _text(data.get("company"), "company", 200),
           "category": category,
           "what": _text(data.get("what"), "what", 1000),
           "buyer": _text(data.get("buyer"), "buyer", 400),
           "price": _text(data.get("price"), "price", 400),
           "replicable": _text(data.get("replicable"), "replicable", 800),
           "effort": effort,
           "moat": _text(data.get("moat"), "moat", 800),
           "risk": _text(data.get("risk"), "risk", 800),
           "why_not_obvious": _text(data.get("why_not_obvious"), "why_not_obvious", 800),
           "sources": sources, "recorded_at": now()}
    rows = [old for old in rows if old.get("id") != ident]
    rows.append(row)
    _write_jsonl(path, rows)
    return row


def add_excluded(root, data):
    """The rejection list: the obvious ideas, and why they are not worth the weeks."""
    idea = _text(data.get("idea"), "idea", 300)
    category = _text(data.get("category"), "category", 60, allow_empty=True).lower()
    row = {"idea": idea, "category": category,
           "why": _text(data.get("why"), "why", 1000), "recorded_at": now()}
    path = base(root) / "excluded.jsonl"
    rows = _jsonl(path)
    rows = [old for old in rows if str(old.get("idea", "")).strip().lower() != idea.strip().lower()]
    rows.append(row)
    _write_jsonl(path, rows)
    body = "# 排除清单（惯性想法与不做的理由）\n\n" + "\n".join(
        f"- **{old.get('idea')}**" + (f"（{old.get('category')}）" if old.get("category") else "")
        + f"：{old.get('why')}" for old in rows) + "\n"
    _save(base(root) / "excluded.md", body)
    return row


def shortlist(root, data):
    candidates = {row.get("id"): row for row in _jsonl(base(root) / "candidates.jsonl")}
    absent = missing(root, "shortlist")
    if absent:
        raise ValueError(f"Cannot shortlist yet: {', '.join(absent)} missing. "
                         + " ".join(NEEDS[key] for key in absent))
    picks = data.get("picks")
    if not isinstance(picks, list):
        raise ValueError("picks must be a list")
    low, high = SHORTLIST_RANGE
    if not low <= len(picks) <= high:
        raise ValueError(f"picks must contain {low}..{high} entries; the full list already exists in "
                         "candidates.jsonl")
    rows, seen = [], set()
    for pick in picks:
        if not isinstance(pick, dict):
            raise ValueError("each pick must be an object with id, why and first_experiment")
        ident = _clean_id(pick.get("id"), "pick id")
        candidate = candidates.get(ident)
        if candidate is None:
            raise ValueError(f"Unknown candidate id {ident}: only registered candidates can be shortlisted.")
        if ident in seen:
            raise ValueError(f"Duplicate pick {ident}")
        seen.add(ident)
        rows.append({"id": ident, "name": candidate.get("name"), "category": candidate.get("category"),
                     "why": _text(pick.get("why"), "why", 1000),
                     "first_experiment": _text(pick.get("first_experiment"), "first_experiment", 1000)})
    body = "\n".join(
        ["# 候选清单", "",
         f"- 候选池：{len(candidates)} 个，覆盖 {len({row.get('category') for row in candidates.values()})} 个类别",
         f"- 排除的惯性想法：{len(_jsonl(base(root) / 'excluded.jsonl'))} 条（见 excluded.md）",
         f"- 生成时间：{now()}", ""]
        + [f"## {position}. {row['name']}（{row['category']}）" + f"\n\n- 为什么：{row['why']}"
           + f"\n- 第一个实验：{row['first_experiment']}" for position, row in enumerate(rows, 1)]) + "\n"
    _save(base(root) / "shortlist.md", body)
    _save(base(root) / "shortlist.json", json.dumps({"picks": rows, "written_at": now()},
                                                    ensure_ascii=False, indent=2))
    return {"picks": rows}


def prompt(state, root):
    """One stage's contract, and the anti-inertia rules that shape every stage."""
    state = clean(state)
    stage = state["stage"]
    found = present(root)
    tally = found["tally"]
    lines = [
        f"\nBusiness scanning mode: you are NOT judging one idea, you are sweeping a market for payable "
        f"products a small team could rebuild, now at **{LABELS[stage]}** ({stage}). Stages: "
        + " → ".join(LABELS[key] for key in STAGES) + ".",
        "The subject is 国内成熟的中小公司: companies that already charge money and still exist. Look at their "
        "product pages, pricing pages, marketplace listings, app stores, review and community threads. Read "
        "widely — this mode is meant to touch many pages, and one page never justifies a candidate.",
        "惯性思维是这个模式的头号敌人。不要在同一个池子里找二十个变体：",
        f"- 每个类别最多 {MAX_PER_CATEGORY} 个候选，超过就会被工具直接拒绝；",
        f"- 候选清单要求至少 {MIN_CANDIDATES} 个候选、覆盖至少 {MIN_CATEGORIES} 个类别；",
        f"- 必须用 scout_exclude 写下至少 {MIN_EXCLUDED} 个你主动放弃的明显想法和理由（AI 套壳聊天、又一个 "
        "Notion 模板、通用 CRM、通用记账…），放弃理由要具体；",
        "- 每个候选要写 why_not_obvious：它为什么不是第一反应会想到的那个东西；",
        "- 每个候选要写 risk：它最可能怎么死。写不出这一条的候选不算候选。",
        "Artifacts live in .eca/scout/: criteria.md, sources.jsonl, candidates.jsonl, excluded.md, "
        "shortlist.md/.json. .eca is a protected path, so use scout_doc for criteria.md and notes.md; the "
        "lists are written by their own tools.",
        "Only public material. Do not invent prices, company names or user numbers — if you could not read it, "
        "leave it out or say it is unknown. A registered page proves the record exists, not that the company is "
        "healthy.",
    ]
    if stage == "criteria":
        lines.append("Now: write criteria.md before searching. What 'small team' means here (people, time, "
                     "money), what you refuse to consider (heavy sales, regulated licences, platform-locked, "
                     "needs a sales team), and what evidence makes a candidate payable. Save with "
                     "scout_doc(name=\"criteria.md\").")
    elif stage == "sweep":
        lines.append(f"Now: produce breadth. Register at least {MIN_CANDIDATES_EARLY} candidates with "
                     "scout_candidate, one industry at a time, and keep a running category tally so you notice "
                     "when you are circling one pool. Do not judge yet — record, then move on.")
    elif stage == "screen":
        lines.append(f"Now: reach {MIN_CANDIDATES} candidates over {MIN_CATEGORIES}+ categories, and write the "
                     "rejection list with scout_exclude. Name the obvious ideas explicitly: the ones you would "
                     "have proposed without any research, plus the categories everyone is crowding.")
    else:
        lines.append(f"Now: pick {SHORTLIST_RANGE[0]}–{SHORTLIST_RANGE[1]} with scout_shortlist. For each: why it "
                     "beat the others, and one minimal first experiment (who to ask, what to show, what price to "
                     "test, the pass/fail line). A shortlist of ideas with no first experiment is a listicle.")
    if found["candidates_rows"]:
        detailed = ", ".join(f"{key} {value}" for key, value in sorted(tally.items()))
        lines.append(f"Candidates so far: {len(found['candidates_rows'])} across {len(tally)} categories "
                     f"({detailed}).")
    if found["excluded_rows"]:
        lines.append(f"Rejected so far: {len(found['excluded_rows'])}.")
    if state["history"]:
        lines.append("Stage history: " + "; ".join(
            f"{entry.get('from')}→{entry.get('to')} ({entry.get('note') or 'no note'})"
            for entry in state["history"][-3:]))
    return "\n".join(lines) + "\n"
