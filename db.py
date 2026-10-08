"""Supabase client connection."""
import sys

from supabase import create_client

from config import get_supabase_config

_client = None


def get_client():
    """Return a single shared Supabase client, creating it on first use."""
    global _client
    if _client is None:
        cfg = get_supabase_config()
        try:
            _client = create_client(cfg["url"], cfg["key"])
        except Exception as e:
            sys.exit(
                "Could not create a Supabase client.\n"
                f"Details: {e}\n"
                "Check the [supabase] url and key in config.ini."
            )
    return _client
