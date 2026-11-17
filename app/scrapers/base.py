import ipaddress
import logging
import re
import socket
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _is_global_public_ip(ip_str: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_str.strip("[]"))
        return not (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )
    except ValueError:
        return False


def is_safe_public_url(raw_url: str) -> bool:
    """Blocks non-HTTP(S) schemes and private/loopback/metadata/link-local SSRF targets."""
    try:
        parsed = urlparse(str(raw_url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        host = parsed.hostname.lower().strip("[]")
        if (
            host in ("localhost", "localhost.localdomain", "metadata.google.internal", "169.254.169.254")
            or host.endswith(".local")
            or host.endswith(".internal")
        ):
            return False
        try:
            ipaddress.ip_address(host)
            return _is_global_public_ip(host)
        except ValueError:
            pass
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not infos:
            return False
        return all(_is_global_public_ip(info[4][0]) for info in infos)
    except Exception:
        return False

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def matches_filter_rules(title: str, include_keywords: str, exclude_keywords: str) -> Tuple[bool, str]:
    """
    Evaluates whether a product title matches include rules and does NOT match exclude rules.
    Returns (is_match, reason).
    """
    clean_title = title.lower()

    # Parse include terms
    includes = [k.strip().lower() for k in include_keywords.split(",") if k.strip()]
    excludes = [k.strip().lower() for k in exclude_keywords.split(",") if k.strip()]

    # 1. Check exclusions first
    for ex in excludes:
        if ex in clean_title:
            return False, f"Excluded by rule: '{ex}' matched in '{title}'"

    # 2. Check inclusions if any exist
    if includes:
        matched_inc = False
        for inc in includes:
            if inc in clean_title:
                matched_inc = True
                break
        if not matched_inc:
            return False, f"Did not match any required include keywords: {includes}"

    return True, "Passed filters"
