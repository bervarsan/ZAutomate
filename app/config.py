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

ZaConfig = namedtuple("ZaConfig", [
    "cache_dir",
    "copy_timeout",
    "cache_max_entries",
    "fallback_dir",
    "stall_seconds"
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


def _get_float(name, default):
    """Read a float environment variable with fallback."""
    value = os.environ.get(name)
    if value is None:
        return default

    try:
        return float(value)
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


def load_za_config():
    """Load file cache, fallback and diagnostics config from environment variables."""
    default_cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "zautomate")

    return ZaConfig(
        cache_dir=os.environ.get("ZA_CACHE_DIR", default_cache_dir),
        copy_timeout=_get_float("ZA_COPY_TIMEOUT", 90.0),
        cache_max_entries=_get_int("ZA_CACHE_MAX_ENTRIES", 300),
        fallback_dir=os.environ.get("ZA_FALLBACK_DIR"),
        stall_seconds=_get_int("ZA_STALL_SECONDS", 30)
    )


madao_config = load_madao_config()
za_config = load_za_config()
