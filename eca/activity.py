"""Bounded, content-free stream telemetry shared by all model adapters."""
import math
import re
import time


def tool_target(args):
    """Only the operation's subject, never file contents or a full argument dump."""
    if not isinstance(args, dict):
        return ''
    parts = []
    for key in ('command', 'path', 'include', 'pattern', 'query', 'url', 'uri', 'symbol',
                'operation', 'server', 'tool', 'name', 'title', 'id', 'preview_id', 'task'):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            # Known model credentials are additionally redacted by DesktopRPC.safe.
            value = re.sub(r'(?i)(https?://)[^/\s]+@', r'\1[redacted]@', value)
            value = re.sub(r'(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s&;]+',
                           r'\1[redacted]', value)
            parts.append(' '.join(value.split())[:180])
        if len(parts) == 2 or key == 'command' and parts:
            break
    return ' · '.join(parts)


class StreamActivity:
    """Estimate live output rate, replacing counts with provider usage at finish.

    The live heuristic is ASCII / 4 + non-ASCII / 1.5, not a tokenizer or billing
    count. Speed uses first-to-last content delta time, excluding request wait,
    tool execution and trailing usage packets. A single burst has no speed.
    """
    def __init__(self, request_id, emit, clock=time.perf_counter):
        self.request_id, self.emit, self.clock = request_id, emit, clock
        self.started = clock()
        self.first = self.last = None
        self.last_emit = self.started
        self.phase = self.tool = ''
        self.units = 0.0
        self.counts = dict(reasoning_chars=0, text_chars=0, tool_argument_chars=0)
        self.updates = 0
        self.opaque_reasoning = False

    def observe(self, *, text='', reasoning='', arguments='', tool='', phase=''):
        now = self.clock()
        if phase == 'thinking' and not reasoning:
            self.opaque_reasoning = True
        previous = (self.phase, self.tool)
        for key, value in (('text_chars', text), ('reasoning_chars', reasoning),
                           ('tool_argument_chars', arguments)):
            self.counts[key] += len(value)
            ascii_count = sum(ord(c) < 128 for c in value)
            self.units += ascii_count / 4 + (len(value) - ascii_count) / 1.5
        if text or reasoning or arguments:
            if self.first is None:
                self.first = now
            self.last = now
            self.updates += 1
        self.phase = phase or ('tool_arguments' if tool or arguments else
                              'responding' if text else 'thinking' if reasoning else self.phase)
        self.tool = tool if self.phase == 'tool_arguments' else ''
        if self.phase and ((self.phase, self.tool) != previous or now-self.last_emit >= .25):
            self.emit('model_activity', self.snapshot())
            self.last_emit = now

    def snapshot(self, usage=None):
        duration = self.last-self.first if self.first is not None and self.last is not None else 0
        actual = (usage or {}).get('completion_tokens', (usage or {}).get('output_tokens'))
        reported = type(actual) is int and actual >= 0
        details = (usage or {}).get('completion_tokens_details') or (usage or {}).get('output_tokens_details') or {}
        hidden_tokens = details.get('reasoning_tokens', 0) if isinstance(details, dict) else 0
        unmeasured = reported and (self.opaque_reasoning or
            isinstance(hidden_tokens, (int, float)) and hidden_tokens > 0 and not self.counts['reasoning_chars'])
        tokens = actual if reported else math.ceil(self.units)
        return dict(request_id=self.request_id, phase=self.phase or 'waiting_model', tool=self.tool,
                    **self.counts, estimated_output_tokens=math.ceil(self.units),
                    output_tokens=actual if reported else None,
                    throughput_source='unavailable' if unmeasured else 'provider' if reported else 'estimate',
                    throughput_unavailable_reason='unobserved_reasoning' if unmeasured else None,
                    tokens_per_second=round(tokens/duration, 1) if not unmeasured and duration >= .25 and self.updates >= 2 else None,
                    generation_ms=round(duration*1000),
                    first_response_ms=round((self.first-self.started)*1000) if self.first is not None else None)
