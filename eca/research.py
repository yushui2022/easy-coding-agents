"""Seven-stage CS research workflow: stages, handoff artifacts and the gates.

The stages are state the model can only move with ``research_stage``, and the
gates are the point of this module: a report is refused while a citation was
never registered, a claim has no evidence, or a reproduction deviation was never
written down. A rule that lives only in the prompt is a wish; these rules read
the files on disk.

Everything is stored under ``<project>/.eca/research`` so the user can read,
diff, back up or delete it — the artifacts are the deliverable, not the chat.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import httpx
from xml.etree import ElementTree as ET

STAGES = ("proposal", "search", "reading", "reproduction", "experiment", "writing", "presentation")
LABELS = {"proposal": "选题", "search": "检索", "reading": "精读", "reproduction": "复现",
          "experiment": "实验", "writing": "写作", "presentation": "汇报"}
CLAIM_STATUSES = ("asserted", "verified", "contradicted", "unverified")
REPRO_OUTCOMES = ("reproduced", "partial", "incomparable", "uncertain")
SOURCE_KINDS = ("doi", "arxiv", "url")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_FILE = 2_000_000
MAX_TEXT = 4000

# What must already exist before a stage may be entered. Written as data so the
# refusal message can name the missing artifact instead of saying "not allowed".
REQUIRES = {
    "proposal": (),
    "search": ("proposal",),
    "reading": ("proposal", "sources"),
    "reproduction": ("sources", "reading"),
    "experiment": ("reading",),
    "writing": ("claims",),
    "presentation": ("report",),
}
NEEDS = {
    "proposal": "write .eca/research/proposal.md first: the research question, hypotheses, scope, feasibility and ethics",
    "sources": "register at least one source with research_source (a DOI/arXiv id is verified online, never from memory)",
    "reading": "write at least one reading card under .eca/research/reading/<source-id>.md",
    "claims": "record at least one claim with research_claim and attach a source id or run id to it",
    "report": "write .eca/research/report.md before asking for a presentation or a final sign-off",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def base(root):
    return Path(root) / ".eca" / "research"


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


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8")


def _clean_id(value, label="id"):
    if not isinstance(value, str) or not ID_PATTERN.match(value.strip().lower()):
        raise ValueError(f"{label} must be 1-64 chars of lowercase letters, digits, '.', '_' or '-'")
    return value.strip().lower()


def _text(value, label, limit=MAX_TEXT, allow_empty=False):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    value = value.strip()
    if not value and not allow_empty:
        raise ValueError(f"{label} cannot be empty")
    if len(value) > limit:
        raise ValueError(f"{label} is limited to {limit} characters")
    return value


def stage_list():
    return [{"id": key, "label": LABELS[key]} for key in STAGES]


def clean(state):
    """Normalise stored stage state; an unknown stage falls back to proposal."""
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


def present(root):
    """Which artifacts exist, so a gate can name what is missing."""
    folder = base(root)
    sources = _jsonl(folder / "sources.jsonl")
    claims = _jsonl(folder / "claims.jsonl")
    runs = sorted((folder / "runs").glob("*.json")) if (folder / "runs").is_dir() else []
    reading = sorted((folder / "reading").glob("*.md")) if (folder / "reading").is_dir() else []
    return {
        "proposal": bool(_read(folder / "proposal.md").strip()),
        "sources": bool(sources),
        "reading": bool(reading),
        "claims": bool([row for row in claims if row.get("sources") or row.get("runs")]),
        "runs": bool(runs),
        "report": bool(_read(folder / "report.md").strip()),
        "deviations": bool(_read(folder / "deviations.md").strip()),
        "sources_rows": sources, "claims_rows": claims,
        "run_files": runs, "reading_files": reading,
    }


def counts(root):
    found = present(root)
    verified_sources = [row for row in found["sources_rows"] if row.get("verified") is True]
    verified_claims = [row for row in found["claims_rows"] if row.get("status") == "verified"]
    return {"sources": len(found["sources_rows"]), "verified_sources": len(verified_sources),
            "claims": len(found["claims_rows"]), "verified_claims": len(verified_claims),
            "runs": len(found["run_files"]), "reading": len(found["reading_files"]),
            "report": found["report"], "deviations": found["deviations"]}


def artifacts(root):
    """Flat, read-only listing for the UI; sizes only, contents stay on demand."""
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
    return {"stage": state["stage"], "label": LABELS[state["stage"]], "stages": stage_list(),
            "history": state["history"], "counts": counts(root), "artifacts": artifacts(root)}


def missing(root, target):
    found = present(root)
    return [key for key in REQUIRES[target] if not found[key]]


def enter(root, state, target, note=""):
    """Move the workflow to ``target``; a backward move must say why."""
    if target not in STAGES:
        raise ValueError(f"stage must be one of: {', '.join(STAGES)}")
    state = clean(state)
    current, wanted = STAGES.index(state["stage"]), STAGES.index(target)
    if wanted == current:
        return state
    note = _text(note, "note", 500, allow_empty=True)
    if wanted < current and not note:
        raise ValueError(f"Moving back from {state['stage']} to {target} changes what the earlier "
                         "artifacts mean, so pass a note explaining why (a review narrowing the topic, "
                         "a reproduction that failed).")
    absent = missing(root, target)
    if absent:
        raise ValueError(f"Cannot enter {target}: {', '.join(absent)} missing. "
                         + " ".join(NEEDS[key] for key in absent))
    state["history"].append({"from": state["stage"], "to": target, "at": now(), "note": note})
    state["stage"] = target
    # Mirror the stage into the artifact folder: the session state is the source of
    # truth, but a research folder that cannot say where it stands is hard to hand
    # to anyone else or to read after a restore.
    folder = base(root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stage.json").write_text(json.dumps(
        {"stage": target, "updated_at": now(), "history": state["history"][-40:]},
        ensure_ascii=False, indent=2), "utf-8")
    return state


def add_source(root, source):
    """Register one source. ``verified`` may only be true for an online check."""
    ident = _clean_id(source.get("id"), "source id")
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(SOURCE_KINDS)}")
    url = _text(source.get("url"), "url", 2000)
    if not url.startswith("https://"):
        raise ValueError("source url must be https")
    row = {"id": ident, "kind": kind, "url": url,
           "title": _text(source.get("title"), "title", 400),
           "year": _text(source.get("year"), "year", 16, allow_empty=True),
           "authors": _text(source.get("authors"), "authors", 400, allow_empty=True),
           "fetched_at": now(), "verified": source.get("verified") is True,
           "note": _text(source.get("note"), "note", 500, allow_empty=True)}
    path = base(root) / "sources.jsonl"
    rows = [old for old in _jsonl(path) if old.get("id") != ident]
    rows.append(row)
    _write_jsonl(path, rows)
    return row


def add_claim(root, claim):
    ident = _clean_id(claim.get("id"), "claim id")
    status = claim.get("status") or "asserted"
    if status not in CLAIM_STATUSES:
        raise ValueError(f"claim status must be one of: {', '.join(CLAIM_STATUSES)}")
    sources = claim.get("sources") or []
    runs = claim.get("runs") or []
    if not isinstance(sources, list) or not isinstance(runs, list):
        raise ValueError("sources and runs must be lists of ids")
    sources = [_clean_id(value, "source id") for value in sources][:12]
    runs = [_clean_id(value, "run id") for value in runs][:12]
    path = base(root) / "sources.jsonl"
    known = {row.get("id"): row for row in _jsonl(path)}
    unknown = [value for value in sources if value not in known]
    if unknown:
        raise ValueError(f"Unregistered source(s): {', '.join(unknown)}. Register each with research_source "
                         "first; a citation that was never fetched cannot be verified later.")
    if status == "verified" and not (sources or runs):
        raise ValueError("A verified claim needs at least one source id or run id. Use 'asserted' or "
                         "'unverified' until there is evidence.")
    if status == "verified":
        weak = [value for value in sources if known[value].get("verified") is not True]
        if weak and not runs:
            raise ValueError(f"Source(s) {', '.join(weak)} were registered without an online check. "
                             "Verify the DOI/arXiv id, or add a run id, before marking this claim verified.")
    row = {"id": ident, "claim": _text(claim.get("claim"), "claim", 2000), "status": status,
           "sources": sources, "runs": runs, "updated_at": now(),
           "note": _text(claim.get("note"), "note", 500, allow_empty=True)}
    claims_path = base(root) / "claims.jsonl"
    rows = [old for old in _jsonl(claims_path) if old.get("id") != ident]
    rows.append(row)
    _write_jsonl(claims_path, rows)
    return row


def add_run(root, run):
    ident = _clean_id(run.get("id"), "run id")
    outcome = run.get("outcome")
    if outcome not in REPRO_OUTCOMES:
        raise ValueError(f"outcome must be one of: {', '.join(REPRO_OUTCOMES)}")
    matches = run.get("matches_paper")
    if not isinstance(matches, bool):
        raise ValueError("matches_paper must be true or false")
    if not matches:
        _text(run.get("note"), "note (required when matches_paper is false)")
    row = {"id": ident, "label": _text(run.get("label"), "label", 300),
           "command": _text(run.get("command"), "command", 2000),
           "exit_code": run.get("exit_code") if type(run.get("exit_code")) is int else None,
           "metrics": run.get("metrics") if isinstance(run.get("metrics"), dict) else {},
           "outcome": outcome, "matches_paper": matches,
           "claims": [_clean_id(value, "claim id") for value in (run.get("claims") or [])][:12],
           "note": _text(run.get("note"), "note", 1000, allow_empty=True), "at": now()}
    folder = base(root) / "runs"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{ident}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), "utf-8")
    return row


# .eca is a protected path for read/write/edit, and it holds the session store, so
# research documents get their own tool with an explicit name allowlist instead of
# opening the whole directory to arbitrary writes.
DOCUMENTS = ("proposal.md", "deviations.md", "report.md", "evidence-matrix.csv",
             "claim-to-artifact.json", "search-log.jsonl", "slides/outline.md")
READING_CARD = re.compile(r"^reading/([a-z0-9][a-z0-9._-]{0,63})\.md$")
MAX_DOC = 400_000


def write_doc(root, name, content, append=False):
    """Write one named research document; nothing else under .eca is writable."""
    if not isinstance(name, str):
        raise ValueError("name must be text")
    name = name.strip().replace("\\", "/").lstrip("./")
    card = READING_CARD.match(name)
    if name not in DOCUMENTS and not card:
        raise ValueError("name must be one of: " + ", ".join(DOCUMENTS) + ", or reading/<source-id>.md")
    body = _text(content, "content", MAX_DOC, allow_empty=True)
    if card:
        known = {row.get("id") for row in _jsonl(base(root) / "sources.jsonl")}
        if card.group(1) not in known:
            raise ValueError("reading card " + name + " belongs to an unregistered source. Register it "
                             "with research_source first, so a card cannot be filed for a paper nobody fetched.")
    target = base(root) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if append:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(body if body.endswith("\n") else body + "\n")
    else:
        target.write_text(body, "utf-8")
    return {"name": name, "bytes": target.stat().st_size, "appended": append}

CITATION = re.compile(r"\[src:\s*([a-z0-9][a-z0-9._-]{0,63})\s*\]", re.I)


def check_report(root, kind="paper"):
    """Refuse a report whose evidence is not actually on disk."""
    if kind not in ("paper", "slides"):
        raise ValueError("kind must be paper or slides")
    folder = base(root)
    target = folder / ("report.md" if kind == "paper" else "slides" / "outline.md")
    body = _read(target)
    if not body.strip():
        raise ValueError(f"Write {target.relative_to(root).as_posix()} first; this check reads the file, "
                         "it does not invent one.")
    found = present(root)
    known = {row.get("id") for row in found["sources_rows"]}
    problems = []
    cited = {value.lower() for value in CITATION.findall(body)}
    unregistered = sorted(cited - known)
    if unregistered:
        problems.append("Unregistered citation(s) " + ", ".join(unregistered)
                        + ": register them with research_source, or remove the [src:…] marker.")
    if not cited and found["claims_rows"]:
        problems.append("No [src:ID] markers found; every factual claim needs a citation that the "
                        "reader can follow back to .eca/research/sources.jsonl.")
    verified_claims = [row for row in found["claims_rows"] if row.get("status") == "verified"]
    bare = [row.get("id") for row in verified_claims if not (row.get("sources") or row.get("runs"))]
    if bare:
        problems.append("Claim(s) " + ", ".join(str(value) for value in bare)
                        + " are marked verified without evidence.")
    mismatched = [path.stem for path in found["run_files"]
                  if json.loads(_read(path) or "{}").get("matches_paper") is False]
    if mismatched and not found["deviations"]:
        problems.append("Run(s) " + ", ".join(mismatched) + " did not match the paper, but "
                        "deviations.md does not exist. Record every deviation before reporting.")
    if mismatched and found["deviations"]:
        deviations = _read(folder / "deviations.md")
        missing_notes = [name for name in mismatched if name not in deviations]
        if missing_notes:
            problems.append("deviations.md does not mention run(s) " + ", ".join(missing_notes) + ".")
    unverified = [row.get("id") for row in found["claims_rows"]
                  if row.get("status") == "asserted"]
    if unverified:
        problems.append("Claim(s) " + ", ".join(str(value) for value in unverified)
                        + " are still 'asserted': mark them verified with evidence, or 'unverified' and "
                        "label them as such in the text.")
    if problems:
        raise ValueError("Report check failed:\n- " + "\n- ".join(problems))
    return {"ok": True, "kind": kind, "file": target.relative_to(root).as_posix(),
            "citations": sorted(cited), "claims": len(found["claims_rows"]),
            "runs": len(found["run_files"]), "note": "A registered source is a real record, not proof "
            "that it supports the claim; that judgement is the author's."}


async def verify(tools, kind, identifier):
    """Resolve a DOI or arXiv id online. Guesses are refused, not remembered."""
    if kind not in ("doi", "arxiv"):
        raise ValueError("verify supports doi or arxiv ids only")
    ident = _text(identifier, "identifier", 200).strip()
    if kind == "doi":
        url = "https://api.crossref.org/works/" + ident.rstrip("/")
    else:
        url = "https://export.arxiv.org/api/query?id_list=" + ident
    from .web import BASE_HEADERS, TIMEOUT, proxy_of, public_url
    proxy = proxy_of(tools.settings)
    approve = getattr(tools, "approve_web", tools.approve)
    if await approve("Verify this citation online? The identifier is sent to the public metadata API.",
                     f"{kind}:{ident}") is not True:
        raise ValueError("Denied by user. Nothing was verified; do not mark this source or claim verified.")
    target = httpx.URL(url)
    host = target.host
    headers = {**BASE_HEADERS, "Accept": "application/json,application/atom+xml", "Host": host}
    if proxy:
        request, extensions = target, {}
    else:
        address = await public_url(url)
        request, extensions = target.copy_with(host=address), {"sni_hostname": host}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, trust_env=False,
                                 headers=BASE_HEADERS, proxy=proxy) as client:
        async with client.stream("GET", request, headers=headers, extensions=extensions) as response:
            if response.status_code == 404:
                raise ValueError(f"{kind}:{ident} was not found. Do not cite it; check the identifier "
                                 "or find the real record.")
            if response.status_code != 200:
                raise ValueError(f"Metadata lookup returned HTTP {response.status_code}. The citation "
                                 "stays unverified; do not invent its details.")
            raw = await response.aread()
    if len(raw) > MAX_FILE:
        raise ValueError("Metadata response was too large to trust")
    if kind == "doi":
        data = json.loads(raw.decode("utf-8", "replace")).get("message", {})
        parts = data.get("issued", {}).get("date-parts") or [[None]]
        authors = ", ".join(" ".join(filter(None, [row.get("given"), row.get("family")]))
                            for row in (data.get("author") or [])[:6])
        return {"title": (data.get("title") or [""])[0][:400], "year": str(parts[0][0] or ""),
                "authors": authors[:400], "url": data.get("URL") or f"https://doi.org/{ident}"}
    root = ET.fromstring(raw.decode("utf-8", "replace"))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = root.find("a:entry", ns)
    if entry is None:
        raise ValueError(f"arXiv:{ident} returned no record. Check the identifier.")
    title = " ".join((entry.findtext("a:title", "", ns) or "").split())
    if not title or title.lower() == "error":
        raise ValueError(f"arXiv:{ident} has no usable title; do not cite it.")
    published = entry.findtext("a:published", "", ns) or ""
    authors = ", ".join((node.findtext("a:name", "", ns) or "")
                        for node in entry.findall("a:author", ns))[:400]
    return {"title": title[:400], "year": published[:4], "authors": authors,
            "url": f"https://arxiv.org/abs/{ident}"}


def prompt(state, root):
    """One stage's contract, never all seven at once."""
    state = clean(state)
    stage = state["stage"]
    found = present(root)
    lines = [f"\nResearch mode: you are running a seven-stage CS research workflow, now at "
             f"**{LABELS[stage]}** ({stage}). Stages: "
             + " → ".join(f"{LABELS[key]}" for key in STAGES) + ".",
             "Artifacts live in .eca/research/ and are the deliverable: proposal.md, sources.jsonl, "
             "reading/<id>.md, evidence-matrix.csv, claims.jsonl, claim-to-artifact.json, runs/<id>.json, "
             "deviations.md, report.md, slides/outline.md. .eca is a protected path for the file tools, so "
             "write every one of them with research_doc (sources.jsonl, claims.jsonl and runs/ are written by "
             "the research tools themselves).",
             "Never write a citation you have not registered with research_source, and never mark a "
             "claim verified without a source id or run id: research_report reads the files and refuses "
             "the report otherwise.",
             "Moving forward needs the previous stage's artifact. Moving back is allowed and must carry "
             "a note saying why — a review narrowing the topic or a failed reproduction is a real finding."]
    if stage == "proposal":
        lines.append("Now: sharpen the question before searching. Compare 2-3 candidate topics, state the "
                     "gap, the research question, hypotheses, method sketch, data/compute feasibility, "
                     'risks and ethics, then save it with research_doc(name="proposal.md"). '
                     "Do not start a literature sweep yet.")
    elif stage == "search":
        lines.append("Now: run the search protocol. Keep every query in search-log.jsonl, register each "
                     "kept paper with research_source (DOI/arXiv verified online), and note why papers "
                     "were excluded. Depth beats volume: eight verified sources with reasons beat forty "
                     "titles.")
    elif stage == "reading":
        lines.append('Now: read one paper at a time. For each, write a reading card with '
                     'research_doc(name="reading/<source-id>.md") covering the '
                     "claim, method, experimental setup, baselines, numbers, limitations and reproduction "
                     "clues. Record disagreements between papers in evidence-matrix.csv.")
    elif stage == "reproduction":
        lines.append("Now: rebuild the artifact. Audit third-party scripts before running them, pin the "
                     "environment, run in stages, and after each run call research_run with the command, "
                     "exit code, metrics and whether the numbers match the paper. Classify the outcome as "
                     "reproduced, partial, incomparable or uncertain — never 'proves the paper'.")
    elif stage == "experiment":
        lines.append("Now: design your own experiment. State the protocol, check for data leakage and "
                     "benchmark fairness, vary one factor at a time for ablations, and record every run "
                     "with research_run. Report what failed as clearly as what worked.")
    elif stage == "writing":
        lines.append("Now: write report.md from the claim ledger with research_doc. Each factual "
                     "sentence carries a "
                     "[src:ID] marker that exists in sources.jsonl; each result points at a run id. Claims "
                     "still 'asserted' must be resolved or labelled unverified, and every mismatch from "
                     "runs belongs in deviations.md. Finish by calling research_report.")
    else:
        lines.append("Now: build slides/outline.md per deck with research_doc. Separate three voices "
                     "explicitly — what the "
                     "authors claim, what you reproduced, what you measured yourself. Anything unverified "
                     "stays labelled, and every number keeps its source or run id.")
    if found["sources_rows"]:
        lines.append(f"Registered sources: {len(found['sources_rows'])} "
                     f"({sum(1 for row in found['sources_rows'] if row.get('verified'))} verified online).")
    if found["claims_rows"]:
        lines.append(f"Claims: {len(found['claims_rows'])} "
                     f"({sum(1 for row in found['claims_rows'] if row.get('status') == 'verified')} verified).")
    if state["history"]:
        lines.append("Stage history: " + "; ".join(
            f"{entry.get('from')}→{entry.get('to')} ({entry.get('note') or 'no note'})"
            for entry in state["history"][-3:]))
    return "\n".join(lines) + "\n"
