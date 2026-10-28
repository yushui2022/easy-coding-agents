"""Protocol-confirmed failures with safe, body-free messages."""


class OutputLimitError(RuntimeError):
    """Cut off at the output token limit. Carries the prose already streamed so
    the agent can keep it and continue instead of discarding the work."""

    def __init__(self, partial='', pending_tools=False):
        self.partial = partial if isinstance(partial, str) else ''
        self.pending_tools = bool(pending_tools)
        detail = 'incomplete tool call dropped; no tools executed' if self.pending_tools else 'no tools executed'
        super().__init__(f'Model output limit reached; {detail}.')


class ContextLimitError(RuntimeError):
    def __init__(self):
        super().__init__('Provider rejected the context size; no tools executed for this request.')


class StalledStreamError(RuntimeError):
    """A connected stream that stopped producing content (keep-alives do not count)."""
    def __init__(self, seconds):
        super().__init__(f'Provider sent no new content for {seconds} seconds; the stream was '
                         'aborted before any tool ran. Retry, lower the thinking effort, '
                         'or switch model or connection.')


def context_rejection(status, body):
    """Strict protocol signals only; never classify generic HTTP/payload failures."""
    if status not in {400, 413} or not isinstance(body, dict):
        return False
    error = body.get('error', body)
    if not isinstance(error, dict):
        return False
    if error.get('code') in {'context_length_exceeded', 'context_window_exceeded', 'input_too_long'}:
        return True
    return (status == 400 and error.get('type') == 'invalid_request_error' and
            isinstance(error.get('message'), str) and error['message'].lower().startswith('prompt is too long'))
