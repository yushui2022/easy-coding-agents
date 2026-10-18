"""Bounded text matching and single-file batch planning, without disk mutations."""
from bisect import bisect_left
import re


def occurrences(text: str, needle: str) -> list[tuple[int, int]]:
    matches = []
    start = text.find(needle)
    while start >= 0 and len(matches) < 6:
        matches.append((start, start + len(needle)))
        start = text.find(needle, start + 1)  # Overlapping occurrences are ambiguous too.
    return matches


def line_matches(text: str, needle: str) -> list[tuple[int, int]]:
    """Only complete multiline blocks; preserve indentation and internal spaces."""
    bom = int(text.startswith('\ufeff'))
    text = text[bom:]  # read() hides the UTF-8 BOM; preserve it outside the edit range.
    wanted = needle.split('\n')
    ends_newline = needle.endswith('\n')
    if ends_newline:
        wanted.pop()
    if len(wanted) < 2 or sum(bool(line.strip()) for line in wanted) < 2:
        return []
    lines = text.split('\n')
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line) + 1
    clean = [line.rstrip(' \t') for line in wanted]
    # KMP over lines avoids quadratic scans on repeated generated code/blank lines.
    prefix = [0] * len(clean)
    length = 0
    for index in range(1, len(clean)):
        while length and clean[index] != clean[length]:
            length = prefix[length - 1]
        if clean[index] == clean[length]:
            length += 1
        prefix[index] = length
    matches = []
    length = 0
    for last, line in enumerate(lines):
        value = line.rstrip(' \t')
        while length and value != clean[length]:
            length = prefix[length - 1]
        if value == clean[length]:
            length += 1
        if length == len(clean):
            if not ends_newline or last < len(lines) - 1:
                end = offsets[last] + len(lines[last]) + int(ends_newline)
                matches.append((offsets[last - length + 1] + bom, end + bom))
            length = prefix[length - 1]
            if len(matches) >= 6:
                break
    return matches


def failure(text: str, needle: str, matches: list[tuple[int, int]], index: int) -> ValueError:
    lines = text.split('\n')
    numbers = [text.count('\n', 0, start) + 1 for start, _ in matches[:5]]
    if not numbers:
        # Suggestions are evidence for a reread only, never replacement candidates.
        hint = next((line.strip() for line in needle.split('\n') if line.strip()), '')
        numbers = [i + 1 for i, line in enumerate(lines) if hint and hint in line][:5]
    snippets = []
    for number in numbers:
        snippets.extend(f'{i+1}: {lines[i][:160]}' for i in range(max(0, number-2), min(len(lines), number+1)))
    reason = 'ambiguous matches' if matches else 'no unique exact or permitted whole-line match'
    return ValueError(f'Edit {index}: old must match exactly once; {reason}. File unchanged. '
                     'Read a larger unique section; indentation and internal whitespace are not normalized.\n' +
                     ('Candidate/nearby lines (not applied):\n' + '\n'.join(snippets) if snippets else 'No nearby line suggestions.'))


def plan_edits(content: str, edits: list[dict], match_mode: str = 'auto') -> tuple[str, int]:
    if match_mode not in {'auto', 'exact'}:
        raise ValueError('match_mode must be auto or exact')
    if not isinstance(edits, list) or not 1 <= len(edits) <= 100:
        raise ValueError('edits must contain 1..100 replacements')
    for item in edits:
        if (not isinstance(item, dict) or set(item) != {'old', 'new'} or
                not isinstance(item['old'], str) or not item['old'] or not isinstance(item['new'], str)):
            raise ValueError('Each edit requires nonempty old and text new, with no extra keys')
    if sum(len(item['old'].encode('utf-8')) + len(item['new'].encode('utf-8')) for item in edits) > 2_000_000:
        raise ValueError('Combined edit text exceeds 2 MB limit')
    normalized = content.replace('\r\n', '\n').replace('\r', '\n')
    crlf = [match.start() - i for i, match in enumerate(re.finditer('\r\n', content))]
    newline = '\r\n' if '\r\n' in content else ('\r' if '\r' in content else '\n')
    replacements, relaxed = [], 0
    for index, item in enumerate(edits, 1):
        needle = item['old'].replace('\r\n', '\n').replace('\r', '\n')
        matches = occurrences(normalized, needle)
        fallback = False
        if not matches and match_mode == 'auto':
            matches = line_matches(normalized, needle)
            fallback = bool(matches)
        if len(matches) != 1:
            raise failure(normalized, needle, matches, index)
        start, end = matches[0]
        start, end = start + bisect_left(crlf, start), end + bisect_left(crlf, end)
        new = item['new'].replace('\r\n', '\n').replace('\r', '\n').replace('\n', newline)
        replacements.append((start, end, new, index))
        relaxed += int(fallback)
    replacements.sort()
    for previous, current in zip(replacements, replacements[1:]):
        if current[0] < previous[1]:
            raise ValueError(f'Edits {previous[3]} and {current[3]} overlap. File unchanged; all edits must target disjoint original ranges.')
    for start, end, new, _ in reversed(replacements):
        content = content[:start] + new + content[end:]
    return content, relaxed
