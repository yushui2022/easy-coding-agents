"""Work modes: what the tool set is, and which modes may actually change the project.

plan      read/search/plan tools only, never edits, no verification chain.
research  the same read-only tool set, but network reads are taken as consented:
          the mode exists to read many pages, so every fetch would otherwise
          interrupt the work it just asked for.
chat      no tools at all.
code      full tool set.
goal      full tool set plus an agreed objective: still a working mode, so verification,
          repair and code children stay available exactly as in code mode.
"""

MODES = ("code", "plan", "goal", "research", "chat")
WORKING = frozenset({"code", "goal"})
READING = frozenset({"plan", "research"})


def working(mode):
    """True when the mode is allowed to change files and run checks."""
    return mode in WORKING


def reading(mode):
    """True when the mode may inspect the project and the web but not change it."""
    return mode in READING
