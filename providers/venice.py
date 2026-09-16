"""Direct venice adapter using shared measurements and error capture."""
from .base import BaseProvider


class VeniceProvider(BaseProvider):
    provider = "venice"
