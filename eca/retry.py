"""Transient model request failures, never tool execution failures."""
import httpx
from openai import APIConnectionError, APIStatusError


class TransientResponseError(RuntimeError):
    pass


def retryable(error):
    if isinstance(error, (httpx.TransportError, APIConnectionError, TransientResponseError)):
        return True
    if isinstance(error, (httpx.HTTPStatusError, APIStatusError)):
        return error.response.status_code in {408, 429, 500, 502, 503, 504, 529}
    return False
