"""Loads Supabase connection settings from config.ini (same folder as this file)."""
import configparser
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")


def get_supabase_config():
    if not os.path.exists(CONFIG_PATH):
        sys.exit(f"config.ini not found at {CONFIG_PATH}. Please create it (see README.md).")

    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH)

    if "supabase" not in parser:
        sys.exit("config.ini is missing a [supabase] section. See README.md.")

    section = parser["supabase"]
    url = section.get("url", "").strip()
    key = section.get("key", "").strip()

    if not url or not key:
        sys.exit(
            "config.ini is missing your Supabase 'url' and/or 'key'.\n"
            "Get both from your Supabase project: Project Settings > API.\n"
            "Use the 'service_role' (secret) key, not the 'anon' key, "
            "so the app has full read/write access."
        )
    return {"url": url, "key": key}
