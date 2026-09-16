"""Direct ionet adapter using shared measurements and error capture."""
from .base import BaseProvider


class IonetProvider(BaseProvider):
    provider = "ionet"
