"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

# Recognized clothing-size tokens for the standalone-token branch. A token only
# counts as a size if it's one of these — so ordinary words like "a" or "in"
# are never mistaken for a size.
_SIZE_TOKENS = {"xxs", "xs", "s", "m", "l", "xl", "xxl"}

# Light lead-in filler stripped from the description so search_listings scores
# against the meaningful keywords (e.g. "looking for a vintage tee" → "vintage
# tee"). These words never appear in a listing haystack, so leaving them in is
# harmless — we drop them only to keep the parsed description clean.
_FILLER = {
    "i", "im", "i'm", "looking", "for", "a", "an", "the", "some", "find",
    "me", "want", "need", "searching", "search", "show", "in",
}


def _parse_query(query: str) -> dict:
    """
    Extract a free-text description, an optional size, and an optional price
    ceiling from a natural-language query.

    Returns a dict with keys: description (str), size (str | None),
    max_price (float | None) — stored verbatim into session["parsed"].
    """
    lower = query.lower()

    # max_price: a dollar amount after under/below/etc., else a bare "$NN".
    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|max|up to|cheaper than)\s*\$?\s*(\d+(?:\.\d+)?)",
        lower,
    )
    if price_match is None:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", lower)
    if price_match:
        max_price = float(price_match.group(1))

    # size: an explicit "size <token>" phrase wins; otherwise a standalone size
    # token (S/M/L/... or a numeric shoe size) anywhere in the query.
    size = None
    size_phrase = re.search(r"\bsize\s+([a-z0-9]+)\b", lower)
    if size_phrase:
        size = size_phrase.group(1).upper()
    else:
        for token in re.findall(r"\b[a-z]+\b|\b\d{1,2}\b", lower):
            if token in _SIZE_TOKENS:
                size = token.upper()
                break

    # description: the query with the price and size phrases stripped out, then
    # filler words removed so only meaningful keywords remain.
    desc = lower
    desc = re.sub(
        r"(?:under|below|less than|max|up to|cheaper than)\s*\$?\s*\d+(?:\.\d+)?",
        " ",
        desc,
    )
    desc = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", desc)
    desc = re.sub(r"\bsize\s+[a-z0-9]+\b", " ", desc)
    if size_phrase is None and size is not None:
        # Remove the standalone size token we picked up (e.g. trailing " m").
        desc = re.sub(rf"\b{size.lower()}\b", " ", desc)
    desc = re.sub(r"[^\w\s'-]", " ", desc)

    words = [w for w in desc.split() if w and w not in _FILLER]
    description = " ".join(words).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: Initialize the session — single source of truth for this run.
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into description / size / max_price.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: Search the catalog with the parsed parameters.
    session["search_results"] = search_listings(
        parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    # Branch A (empty): no match — set a specific error echoing the filters and
    # return EARLY. Do NOT call suggest_outfit with empty input.
    if not session["search_results"]:
        desc = parsed["description"] or "that"
        bits = [f"any '{desc}'"]
        if parsed["max_price"] is not None:
            bits.append(f"under ${parsed['max_price']:.0f}")
        if parsed["size"]:
            bits.append(f"in size {parsed['size']}")
        session["error"] = (
            f"I couldn't find {' '.join(bits)} right now. "
            "Try removing the size or raising your budget — there are 40 "
            "secondhand pieces in the catalog and looser filters usually "
            "surface a match."
        )
        return session

    # Branch B (non-empty): Step 4 — select the top-scored result.
    session["selected_item"] = session["search_results"][0]

    # Step 5: Suggest an outfit. This tool self-handles the empty-wardrobe case
    # and always returns a non-empty string, so the loop does not branch here.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], wardrobe
    )

    # Step 6: Build the shareable fit card from the outfit + selected item.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: Done — error is None and all output fields are populated.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
