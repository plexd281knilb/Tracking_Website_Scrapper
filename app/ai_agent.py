import os
import re
import json
import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Specialized Bourbon Domain Knowledge Base
BOURBON_KNOWLEDGE_BASE = [
    {
        "pattern": r"jack\s*daniel|coy\s*hill|twice\s*barrel",
        "name": "Jack Daniel's Special & Allocated Releases",
        "includes": "coy hill, twice barreled, special release, heritage barrel, jack daniel's 10, jack daniel's 12, high proof rye, barrel proof special",
        "excludes": "old no 7, gentleman, honey, fire, apple, country cocktails, standard 750ml, premix",
        "reasoning": "Targets allocated Jack Daniel's Limited Releases (Coy Hill, Twice Barreled, 10/12 Yr) while filtering standard core lineup variants."
    },
    {
        "pattern": r"elijah\s*craig|ecbp",
        "name": "Elijah Craig Barrel Proof & Special Releases",
        "includes": "barrel proof, ecbp, A12, B52, C92, 18 year, 23 year, toasted barrel, single barrel barrel proof",
        "excludes": "small batch 94 proof, standard small batch, Elijah Craig rye standard",
        "reasoning": "Focuses on ECBP batch releases (A124, B524, C923 etc.) and age-stated 18/23yr single barrels."
    },
    {
        "pattern": r"george\s*t\s*stagg|btac|stagg",
        "name": "Buffalo Trace Antique Collection & Stagg",
        "includes": "george t stagg, stagg jr, stagg barrel proof, william larue weller, thomas h handy, eagle rare 17, sazerac 18",
        "excludes": "standard buffalo trace, wheatley vodka, benchmark, traveler, benchmark 8",
        "reasoning": "Targets allocated BTAC bottles and uncut/unfiltered Stagg releases."
    },
    {
        "pattern": r"weller",
        "name": "Weller Allocated Lineup",
        "includes": "weller full proof, weller single barrel, weller cypb, weller 12, daniel weller, weller antique 107",
        "excludes": "special reserve standard, green label 750ml common",
        "reasoning": "Filters for highly allocated Weller expressions (Full Proof, CYPB, 12 Year, Single Barrel) while bypassing common Special Reserve stock."
    },
    {
        "pattern": r"pappy|van\s*winkle|rip\s*van",
        "name": "Pappy & Old Rip Van Winkle Family Reserve",
        "includes": "pappy van winkle, old rip van winkle, van winkle special reserve, 10 year, 12 year lot b, 15 year, 20 year, 23 year",
        "excludes": "empty bottle, decanter display, glass decanter",
        "reasoning": "Strictly targets genuine Pappy Van Winkle Family Reserve and Old Rip Van Winkle bottles."
    },
    {
        "pattern": r"midwinter|dram|high\s*west",
        "name": "High West A Midwinter Night's Dram",
        "includes": "midwinter night's dram, midwinters, act 1, act 2, act 3, act 10, act 11, act 12, cask strength high west",
        "excludes": "american prairie bourbon standard, double rye standard",
        "reasoning": "Targets annual Midwinter Night's Dram Act/Scene releases while ignoring core High West Prairie/Rye."
    },
    {
        "pattern": r"parker|four\s*roses\s*le|michter\s*10|king\s*of\s*kentucky|birthday\s*bourbon",
        "name": "Ultra-Allocated Annual Limited Editions",
        "includes": "parker's heritage, king of kentucky, birthday bourbon, michter's 10 year, michter's 20 year, four roses limited edition, lesm",
        "excludes": "four roses yellow label, four roses small batch standard, michter's US1 small batch",
        "reasoning": "Filters for annual grail releases (King of Kentucky, OFBB, Parker's Heritage, Michter's 10/20)."
    }
]


def call_gemini_api(bourbon_name: str, api_key: str) -> Dict[str, Any]:
    """Calls Google Gemini 1.5 Flash API to generate specialized search keywords."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    prompt = (
        f"You are a World-Class Bourbon Sommelier & Web Scraper Search Expert. "
        f"The user wants to track availability for: '{bourbon_name}'. "
        f"Generate optimized search keyword rules to find rare/special release bottles on retail websites while filtering out common/standard bottles. "
        f"Respond ONLY with a raw JSON object with keys: "
        f"'include_keywords' (comma separated string of positive keywords), "
        f"'exclude_keywords' (comma separated string of negative terms to filter standard bottles), and "
        f"'reasoning' (short 1-2 sentence explanation of your strategy)."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                res_json = resp.json()
                text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content)
                return {
                    "bourbon_name": bourbon_name,
                    "preset_matched": "Google Gemini 1.5 Flash Agent 🤖",
                    "include_keywords": parsed.get("include_keywords", ""),
                    "exclude_keywords": parsed.get("exclude_keywords", ""),
                    "reasoning": parsed.get("reasoning", f"Gemini 1.5 generated custom keyword rules for '{bourbon_name}'.")
                }
            else:
                logger.warning(f"Gemini API returned status {resp.status_code}. Falling back to local engine...")
    except Exception as e:
        logger.warning(f"Gemini API request failed: {e}. Falling back to local engine...")

    return None


def generate_smart_keywords(bourbon_name: str) -> Dict[str, Any]:
    """
    AI Bourbon Sommelier Engine: Analyzes a target bourbon name and generates
    optimized positive inclusion terms and negative exclusion terms.
    Checks GEMINI_API_KEY environment variable first.
    """
    clean_name = bourbon_name.strip().lower()

    # 1. Try Google Gemini API if key is set
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        gemini_result = call_gemini_api(bourbon_name, gemini_key)
        if gemini_result:
            return gemini_result

    # 2. Local Domain Knowledge Base search
    for rule in BOURBON_KNOWLEDGE_BASE:
        if re.search(rule["pattern"], clean_name):
            return {
                "bourbon_name": bourbon_name,
                "preset_matched": rule["name"],
                "include_keywords": rule["includes"],
                "exclude_keywords": rule["excludes"],
                "reasoning": rule["reasoning"]
            }

    # 3. Generic Smart Fallback if no specific rule pattern matched
    words = [w for w in re.split(r'\W+', clean_name) if len(w) > 2 and w not in ["the", "and", "bottle", "whiskey", "bourbon"]]
    main_terms = ", ".join(words) if words else clean_name

    return {
        "bourbon_name": bourbon_name,
        "preset_matched": "Built-in Bourbon Intelligence Agent",
        "include_keywords": main_terms,
        "exclude_keywords": "standard, premix, mini, RTD, cocktail, empty bottle, merchandise",
        "reasoning": f"Generated custom keyword filters for '{bourbon_name}' to focus on exact title matches while filtering out merch and premixed cocktails."
    }
