import re
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

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
