"""Direct chutes adapter using shared measurements and error capture."""
from .base import BaseProvider


class ChutesProvider(BaseProvider):
    provider = "chutes"
