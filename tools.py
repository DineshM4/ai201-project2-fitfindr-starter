"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Groq chat model used by the LLM-backed tools (suggest_outfit, create_fit_card).
GROQ_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    # 1. Load the full catalog. Guard the whole thing so the tool never raises.
    try:
        listings = load_listings()
    except Exception:
        return []

    # Build the set of lowercase keywords from the description. Splitting on
    # whitespace gives us individual words to look for ("vintage", "graphic",
    # "tee"); duplicates collapse into a set so each keyword counts once.
    keywords = {word for word in description.lower().split() if word}
    if not keywords:
        return []

    size_filter = size.lower().strip() if size else None

    scored: list[tuple[int, dict]] = []
    for listing in listings:
        # 2a. Price filter — drop anything above the ceiling.
        if max_price is not None and listing["price"] > max_price:
            continue

        # 2b. Size filter — case-insensitive substring test, so "m" matches
        #     "s/m". A listing with no size field is skipped when filtering.
        if size_filter is not None:
            listing_size = str(listing.get("size", "")).lower()
            if size_filter not in listing_size:
                continue

        # 3. Score by keyword overlap. Each searchable field is lowered and
        #    joined into one haystack; we count how many distinct keywords
        #    appear anywhere in it.
        haystack = " ".join(
            [
                listing.get("title", ""),
                listing.get("description", ""),
                " ".join(listing.get("style_tags", [])),
            ]
        ).lower()

        score = sum(1 for keyword in keywords if keyword in haystack)

        # 4. Drop listings with no keyword overlap at all.
        if score > 0:
            scored.append((score, listing))

    # 5. Sort by score, highest first, and return just the listing dicts.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Pull the new item's details into a compact, readable block for the prompt.
    # .get() keeps us safe if a field is missing on the listing dict.
    item_lines = "\n".join(
        [
            f"- Title: {new_item.get('title', 'Unknown item')}",
            f"- Category: {new_item.get('category', 'unknown')}",
            f"- Colors: {', '.join(new_item.get('colors', [])) or 'unspecified'}",
            f"- Style tags: {', '.join(new_item.get('style_tags', [])) or 'none'}",
            f"- Price: ${new_item.get('price', 0):.2f}",
        ]
    )

    # 1. Is the wardrobe empty? Treat a missing 'items' key the same as empty.
    items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    if items:
        # 3. Populated wardrobe — list each piece by name so the LLM can
        #    reference them directly. Notes are included when present.
        wardrobe_lines = []
        for it in items:
            colors = ", ".join(it.get("colors", [])) or "unspecified"
            tags = ", ".join(it.get("style_tags", [])) or "none"
            line = (
                f"- {it.get('name', 'Unnamed piece')} "
                f"({it.get('category', 'unknown')}; colors: {colors}; style: {tags})"
            )
            if it.get("notes"):
                line += f" — note: {it['notes']}"
            wardrobe_lines.append(line)
        wardrobe_block = "\n".join(wardrobe_lines)

        prompt = (
            "You are a personal stylist helping someone style a secondhand item "
            "they're thinking of buying, using clothes they already own.\n\n"
            f"The new item they're considering:\n{item_lines}\n\n"
            f"Their current wardrobe:\n{wardrobe_block}\n\n"
            "Suggest 1-2 complete outfits built around the new item. Reference the "
            "wardrobe pieces by their exact names (e.g. \"pair it with your "
            "Baggy straight-leg jeans\"). Only use pieces that genuinely work with "
            "the new item — colors, category, and vibe should make sense together. "
            "Keep it to a few warm, conversational sentences. Do not invent items "
            "that aren't in their wardrobe."
        )
    else:
        # 2. Empty wardrobe — ask for general styling ideas instead. We append
        #    the "add items" nudge ourselves so it's always present.
        prompt = (
            "You are a personal stylist helping someone style a secondhand item "
            "they're thinking of buying. They haven't added any wardrobe items yet, "
            "so give general styling advice.\n\n"
            f"The new item they're considering:\n{item_lines}\n\n"
            "Suggest what kinds of pieces (categories, colors, vibes) pair well with "
            "this item and what overall looks it suits. Keep it to a few warm, "
            "conversational sentences. Do not reference specific items they own, "
            "since you don't know their wardrobe yet."
        )

    # 4. Call the LLM and return its text. Guard the call so the tool always
    #    returns a non-empty string rather than raising (per the spec).
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        suggestion = (response.choices[0].message.content or "").strip()
    except Exception:
        suggestion = ""

    if not suggestion:
        # Fallback so the pipeline downstream always has something to work with.
        suggestion = (
            f"This {new_item.get('title', 'piece')} is a versatile find — try "
            "pairing it with neutral basics and a layer that matches its vibe to "
            "build an easy everyday look."
        )

    if not items:
        suggestion += (
            "\n\nAdd a few pieces to your wardrobe and I'll tailor outfits to "
            "what you already own."
        )

    return suggestion


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against a missing/empty/whitespace-only outfit. Without an outfit
    #    idea there's nothing to caption, so return a descriptive message rather
    #    than raising or returning an empty string (per the spec).
    if not isinstance(outfit, str) or not outfit.strip():
        return (
            "I can't write a fit card without an outfit idea — try searching "
            "again or pick a different piece."
        )

    # Pull the item details the caption must mention exactly once each.
    # .get() keeps us safe if a field is missing on the listing dict.
    title = new_item.get("title", "this piece") if isinstance(new_item, dict) else "this piece"
    price = new_item.get("price", 0.0) if isinstance(new_item, dict) else 0.0
    platform = new_item.get("platform", "a resale app") if isinstance(new_item, dict) else "a resale app"

    # 2. Build the prompt: hand the LLM the item facts and the outfit, and ask
    #    for a short, authentic OOTD-style caption following the style rules.
    prompt = (
        "You're writing a short, fun caption for a thrifted outfit, like a real "
        "Instagram/TikTok OOTD post (not a product description).\n\n"
        f"The thrifted item:\n"
        f"- Name: {title}\n"
        f"- Price: ${price:.2f}\n"
        f"- Platform: {platform}\n\n"
        f"The styled outfit:\n{outfit}\n\n"
        "Write a 2-4 sentence caption that:\n"
        f"- Mentions the item name (\"{title}\"), the price (${price:.2f}), and "
        f"the platform (\"{platform}\") naturally, exactly once each.\n"
        "- Feels casual and authentic, capturing the specific vibe of the outfit.\n"
        "- Reads like something a real person would post.\n"
        "Return only the caption text, no quotes or labels."
    )

    # 3. Call the LLM at a higher temperature so captions vary across runs. Guard
    #    the call so a failure degrades to a plain assembled caption instead of
    #    raising or returning an empty string.
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
        )
        caption = (response.choices[0].message.content or "").strip()
    except Exception:
        caption = ""

    if not caption:
        # Fallback caption assembled from the item facts so the user always
        # gets a shareable result that still names title, price, and platform.
        caption = (
            f"thrifted this {title} on {platform} for ${price:.2f} ✨ styled it up "
            "and honestly couldn't be happier with the find. #thrifted #ootd"
        )

    return caption
