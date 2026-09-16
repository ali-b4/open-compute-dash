"""Direct darkbloom adapter using shared measurements and error capture."""
from .base import BaseProvider


class DarkbloomProvider(BaseProvider):
    provider = "darkbloom"
