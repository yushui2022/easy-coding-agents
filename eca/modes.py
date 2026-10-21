"""Work modes: what the tool set is, and which modes may actually change the project.

plan  read/search/plan tools only, never edits, no verification chain.
chat  no tools at all.
code  full tool set.
goal  full tool set plus an agreed objective: still a working mode, so verification,
      repair and code children stay available exactly as in code mode.
"""

MODES = ("code", "plan", "goal", "chat")
WORKING = frozenset({"code", "goal"})


def working(mode):
    """True when the mode is allowed to change files and run checks."""
    return mode in WORKING
