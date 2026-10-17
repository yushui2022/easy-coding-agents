"""Protocol-confirmed failures with safe, body-free messages."""


class OutputLimitError(RuntimeError):
    def __init__(self):
        super().__init__('Model output limit reached; incomplete response discarded; no tools executed.')
