"""Provider adapters share the measured direct-API transport."""
from abc import ABC


class BaseProvider(ABC):
    provider: str

    def chat(self, messages: list[dict[str, str]], *, streaming=False, timeout=180,
             request_options=None) -> dict:
        from scripts.manual_request import probe
        return probe(self.provider, '', timeout, streaming, messages=messages,
                     request_options=request_options)
