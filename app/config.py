"""Lightweight runtime configuration helpers."""
from collections import namedtuple
import os

MadaoConfig = namedtuple("MadaoConfig", [
    "ao_driver",
    "ao_bits",
    "ao_channels",
    "ao_rate",
    "ao_byte_format"
])


def _get_int(name, default):
    """Read an integer environment variable with fallback."""
    value = os.environ.get(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def load_madao_config():
    """Load madao runtime config from environment variables."""
    return MadaoConfig(
        ao_driver=os.environ.get("ZA_AO_DRIVER"),
        ao_bits=_get_int("ZA_AO_BITS", 16),
        ao_channels=_get_int("ZA_AO_CHANNELS", 2),
        ao_rate=_get_int("ZA_AO_RATE", 44100),
        ao_byte_format=os.environ.get("ZA_AO_BYTE_FORMAT", "little")
    )


madao_config = load_madao_config()
