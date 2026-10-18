"""Protocol-confirmed failures with safe, body-free messages."""


class OutputLimitError(RuntimeError):
    def __init__(self):
        super().__init__('Model output limit reached; incomplete response discarded; no tools executed.')


class ContextLimitError(RuntimeError):
    def __init__(self):
        super().__init__('Provider rejected the context size; no tools executed for this request.')


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
