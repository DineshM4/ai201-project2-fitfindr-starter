"""
tests/test_tools.py

Pytest unit tests for the three FitFindr tools in tools.py.

Run with:  python -m pytest tests/

"""

from unittest.mock import MagicMock, patch

import pytest

import tools


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def new_item():
    """A representative listing dict, shaped like the real dataset."""
    return {
        "id": "lst_001",
        "title": "Vintage Levi's 501 Jeans — Medium Wash",
        "description": "Classic 501s in a perfect medium wash.",
        "category": "bottoms",
        "style_tags": ["vintage", "classic", "denim"],
        "size": "W30 L30",
        "condition": "good",
        "price": 38.0,
        "colors": ["blue"],
        "brand": "Levi's",
        "platform": "depop",
    }


@pytest.fixture
def populated_wardrobe():
    return {
        "items": [
            {
                "id": "w_001",
                "name": "Baggy straight-leg jeans, dark wash",
                "category": "bottoms",
                "colors": ["dark blue", "indigo"],
                "style_tags": ["denim", "streetwear", "baggy"],
                "notes": "High-waisted, sits above the hip",
            },
            {
                "id": "w_002",
                "name": "White cotton tee",
                "category": "tops",
                "colors": ["white"],
                "style_tags": ["basic", "minimal"],
            },
        ]
    }


@pytest.fixture
def empty_wardrobe():
    return {"items": []}


def _fake_client(content):
    """Build a fake Groq client whose chat completion returns `content`."""
    client = MagicMock()
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


# ── Tool 1: search_listings ─────────────────────────────────────────────────

class TestSearchListings:
    def test_returns_matching_listings(self):
        """Happy path: a real keyword returns non-empty results that match."""
        results = tools.search_listings("vintage jeans")
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, dict) for r in results)

    def test_no_match_returns_empty_list_not_exception(self):
        """Failure mode: gibberish matches nothing → [] (must not raise)."""
        results = tools.search_listings("zzqqxynonsensekeyword")
        assert results == []

    def test_search_returns_results(self):
        results = tools.search_listings(
            "vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_empty_description_returns_empty_list(self):
        """Failure mode: no keywords to score against → []."""
        assert tools.search_listings("") == []
        assert tools.search_listings("   ") == []

    def test_max_price_filters_out_expensive_items(self):
        """Failure mode: price ceiling must exclude pricier listings."""
        results = tools.search_listings("jeans", max_price=10.0)
        assert all(r["price"] <= 10.0 for r in results)

    def test_size_filter_is_case_insensitive_substring(self):
        """Size filter matches case-insensitively; everything returned fits."""
        size = "m"
        results = tools.search_listings("shirt", size=size)
        assert all(size in str(r.get("size", "")).lower() for r in results)

    def test_results_sorted_by_score_descending(self):
        """A multi-keyword query should rank stronger matches first."""
        results = tools.search_listings("vintage denim jeans")

        def score(listing):
            haystack = " ".join(
                [
                    listing.get("title", ""),
                    listing.get("description", ""),
                    " ".join(listing.get("style_tags", [])),
                ]
            ).lower()
            return sum(
                1 for kw in {"vintage", "denim", "jeans"} if kw in haystack
            )

        scores = [score(r) for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_loader_failure_returns_empty_list(self):
        """Failure mode: if load_listings() raises, return [] (no crash)."""
        with patch.object(tools, "load_listings", side_effect=OSError("boom")):
            assert tools.search_listings("jeans") == []


# ── Tool 2: suggest_outfit ───────────────────────────────────────────────────

class TestSuggestOutfit:
    def test_populated_wardrobe_returns_llm_text(self, new_item, populated_wardrobe):
        """Happy path: returns the model's suggestion for a real wardrobe."""
        fake = _fake_client(
            "Pair it with your White cotton tee for an easy look.")
        with patch.object(tools, "_get_groq_client", return_value=fake):
            out = tools.suggest_outfit(new_item, populated_wardrobe)
        assert "White cotton tee" in out
        # The "add items" nudge is only for empty wardrobes.
        assert "Add a few pieces" not in out

    def test_empty_wardrobe_does_not_crash_and_is_non_empty(self, new_item, empty_wardrobe):
        """Failure mode: empty wardrobe → general advice + nudge, never empty."""
        fake = _fake_client("This denim pairs well with neutral basics.")
        with patch.object(tools, "_get_groq_client", return_value=fake):
            out = tools.suggest_outfit(new_item, empty_wardrobe)
        assert isinstance(out, str) and out.strip()
        assert "Add a few pieces" in out

    def test_search_empty_results(self):
        results = tools.search_listings(
            "designer ballgown", size="XXS", max_price=5)
        assert results == []   # empty list, no exception

    def test_missing_items_key_treated_as_empty(self, new_item):
        """Failure mode: a wardrobe dict with no 'items' key behaves as empty."""
        fake = _fake_client("General styling advice here.")
        with patch.object(tools, "_get_groq_client", return_value=fake):
            out = tools.suggest_outfit(new_item, {})
        assert out.strip()
        assert "Add a few pieces" in out

    def test_llm_failure_falls_back_to_non_empty_string(self, new_item, populated_wardrobe):
        """Failure mode: LLM error must degrade to a fallback, not raise."""
        with patch.object(tools, "_get_groq_client", side_effect=RuntimeError("api down")):
            out = tools.suggest_outfit(new_item, populated_wardrobe)
        assert isinstance(out, str) and out.strip()

    def test_empty_llm_content_falls_back(self, new_item, populated_wardrobe):
        """Failure mode: blank model output must trigger the fallback text."""
        fake = _fake_client("")
        with patch.object(tools, "_get_groq_client", return_value=fake):
            out = tools.suggest_outfit(new_item, populated_wardrobe)
        assert out.strip()


# ── Tool 3: create_fit_card ──────────────────────────────────────────────────

class TestCreateFitCard:
    def test_returns_caption_on_valid_input(self, new_item):
        """Happy path: a real outfit string yields the model's caption."""
        fake = _fake_client("Thrifted gold ✨ #ootd")
        with patch.object(tools, "_get_groq_client", return_value=fake):
            out = tools.create_fit_card("Jeans with a white tee", new_item)
        assert out.strip() == "Thrifted gold ✨ #ootd"

    def test_empty_outfit_returns_error_message_not_exception(self, new_item):
        """Failure mode: empty outfit → descriptive error string, no raise."""
        out = tools.create_fit_card("", new_item)
        assert isinstance(out, str) and out.strip()
        assert "can't write a fit card" in out.lower()

    def test_whitespace_outfit_returns_error_message(self, new_item):
        """Failure mode: whitespace-only outfit is treated as empty."""
        out = tools.create_fit_card("   \n  ", new_item)
        assert "can't write a fit card" in out.lower()

    def test_non_string_outfit_returns_error_message(self, new_item):
        """Failure mode: a non-string outfit must not crash the tool."""
        out = tools.create_fit_card(None, new_item)
        assert isinstance(out, str) and "can't write a fit card" in out.lower()

    def test_search_price_filter(self):
        results = tools.search_listings("jacket", size=None, max_price=10)
        assert all(item["price"] <= 10 for item in results)

    def test_llm_failure_falls_back_with_item_facts(self, new_item):
        """Failure mode: LLM error → fallback caption naming the key facts."""
        with patch.object(tools, "_get_groq_client", side_effect=RuntimeError("api down")):
            out = tools.create_fit_card("Jeans with a white tee", new_item)
        assert isinstance(out, str) and out.strip()
        assert new_item["title"] in out
        assert new_item["platform"] in out
        assert f"{new_item['price']:.2f}" in out

    def test_uses_high_temperature_for_varied_captions(self, new_item):
        """Captions must use a high temperature so repeats vary; assert >= 1.0."""
        fake = _fake_client("caption text")
        with patch.object(tools, "_get_groq_client", return_value=fake):
            tools.create_fit_card("Jeans with a white tee", new_item)
        _, kwargs = fake.chat.completions.create.call_args
        assert kwargs["temperature"] >= 1.0
