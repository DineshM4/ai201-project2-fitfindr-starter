# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
The tool searches the 30-item mock listings for secondhand items that match user's keywords, with optional additional size and price filters. All parts of this tool is python only, it filters, scores each listing by keyword overlap and returns the best matches primarily. 

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): Free-text keywords describing the desired item, e.g. `"vintage graphic tee"`. Required. Matched case-insensitively against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): Size string to filter by, e.g. `"M"`. Optional — pass `None` to skip size filtering. Matching is a case-insensitive substring test against the listing's `size` field, so `"M"` matches `"S/M"`.
- `max_price` (float | None): Inclusive price ceiling in dollars, e.g. `30.0`. Optional — pass `None` to skip price filtering. A listing passes when `listing["price"] <= max_price`.

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
The tool returns a `list[dict]` sorted by relevance score (highest first). Each dict has full listing with the following parameters: `id` (str), `title` (str), `description` (str), `category` (str — tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str — excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str — depop/thredUp/poshmark).  

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
If the tool fails or returning nothing, then it returns `[]` rather than raising. Then the planning loop would detect the empty list and returns the session early for safe error handling without crashing.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
This tool takes the top listing from the previous tool and asks Groq to propose 1-2 complete outfits around the new item. When there are specific wardrobe pieces that the user has matching with the item, the tool will reccomend them. If there are none, the tool will give general stlying advice instead. 

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A single listing dict (the top search result — `session["selected_item"]`). Its `title`, `category`, `colors`, `style_tags`, and `price` are read into the prompt.
- `wardrobe` (dict): A wardrobe dict with an `items` key holding a `list[dict]`. Each item has `id`, `name`, `category`, `colors` (list), `style_tags` (list), and optional `notes`. May be empty (`{"items": []}`) — handled explicitly.

**What it returns:**
<!-- Describe the return value -->
The tool retursn a non-empty `str` of natural-language outfit suggestions. With a populated wardrobe(One the user has the required piece of clothing) it references pieces by name (e.g. "pair it with your *Baggy straight-leg jeans* and *Chunky white sneakers*"). With an empty wardrobe it returns general styling ideas (what categories/colors/vibes pair well) plus a note that suggestions get more specific once the user adds items.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
This is the case where the tool will return general syling ideas from the previous section.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
The tool turns the outfit suggesttion and the item detials into a short, shareable, social media style caption.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): The outfit-suggestion string returned by `suggest_outfit()` (`session["outfit_suggestion"]`). Required and must be non-empty.
- `new_item` (dict): The listing dict for the thrifted item (`session["selected_item"]`). The caption mentions its `title`, `price`, and `platform` exactly once each.

**What it returns:**
<!-- Describe the return value -->
The tool returns a `str` of 2–4 sentences usable directly as an Instagram/TikTok caption. This can be casual and authentic, mentioning the item name, price, and platform naturally, and capturing the outfit vibe in specific terms.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If there is an error in terms of data incompleteness, the tool will return an error message instead of crashing. It will never return an empty string.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->
No additional tools are required as of this moment. 

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The planning loop is a fixed, linear pipeline with one early-exit case built in. The order of tools never changes, only the if the exit case is triggered or not. The Logic, step by step:

1. **Initialize.** Call `_new_session(query, wardrobe)`. All result fields start `None`/empty and `error` starts `None`.

2. **Parse the query.** Extract `description`, `size`, and `max_price` from `query` with regex/string parsing:
   - `max_price`: a dollar amount after "under"/"below"/"$" (e.g. `under $30` → `30.0`); else `None`.
   - `size`: a `size <token>` phrase or standalone size token (XS/S/M/L/XL or a numeric shoe size); else `None`.
   - `description`: the query with the price and size phrases stripped out (e.g. `"vintage graphic tee"`).
   - Store all three under `session["parsed"]`.

3. **Call `search_listings(description, size, max_price)`** and store the list in `session["search_results"]`.
   - **Branch A (empty):** if `search_results == []`, set `session["error"]` to a specific no-results message that echoes the parsed filters (see Error Handling table), and `return session` immediately. Do NOT call `suggest_outfit`.
   - **Branch B (non-empty):** set `session["selected_item"] = search_results[0]` (highest-scored match) and continue.

4. **Call `suggest_outfit(selected_item, wardrobe)`** and store the string in `session["outfit_suggestion"]`. This tool self-handles the empty-wardrobe case internally, so the loop does not branch here — it always gets back a non-empty string.

5. **Call `create_fit_card(outfit_suggestion, selected_item)`** and store the string in `session["fit_card"]`. This tool self-handles a missing/empty outfit, so the loop does not branch here either.

6. **Done.** `return session`. The caller checks `session["error"]` first; if it is `None`, `selected_item`, `outfit_suggestion`, and `fit_card` are all populated.

**How it knows it's done:** the pipeline has a fixed number of stages (3 tool calls). It terminates when either the early-exit branch fires after `search_listings`, or all three tools have run and `fit_card` is set. 

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

The agent uses a single `session` dict as the one source of truth for the interaction. At each stage the tool reads from the session and also stores its outputes to the session.

Fields and how they're used:

| Field | Type | Written by | Read by |
|-------|------|-----------|---------|
| `query` | str | `_new_session` | parse step |
| `parsed` | dict (`description`, `size`, `max_price`) | parse step | `search_listings` call |
| `search_results` | list[dict] | `search_listings` | empty-check branch, item selection |
| `selected_item` | dict \| None | item-selection step (`= search_results[0]`) | `suggest_outfit`, `create_fit_card`, UI |
| `wardrobe` | dict | `_new_session` (from caller) | `suggest_outfit` |
| `outfit_suggestion` | str \| None | `suggest_outfit` | `create_fit_card`, UI |
| `fit_card` | str \| None | `create_fit_card` | UI |
| `error` | str \| None | any early-exit branch | caller / UI (checked first) |

Concretely: `search_listings` writes `search_results`; the loop copies `search_results[0]` into `selected_item`; `suggest_outfit` reads `selected_item` + `wardrobe` and writes `outfit_suggestion`; `create_fit_card` reads `outfit_suggestion` + `selected_item` and writes `fit_card`. On any failure the loop writes `error` and returns, leaving downstream fields `None`. State lives for one `run_agent()` call only; each query starts a fresh session.

---

## Error Handling


| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Loop sets `session["error"]` and exits before any LLM tool runs. The message echoes the parsed filters so the user knows what to relax, e.g. *"I couldn't find any 'vintage graphic tee' under $30 in size M right now. Try removing the size or raising your budget — there are 40 secondhand pieces in the catalog and looser filters usually surface a match."* The UI shows this in the listing panel; the outfit and fit-card panels stay empty. |
| suggest_outfit | Wardrobe is empty | Tool does NOT error or return empty. It switches to its general-advice branch and returns styling ideas for the item on its own terms (vibe, what categories/colors pair with it), ending with a nudge: *"Add a few pieces to your wardrobe and I'll tailor outfits to what you already own."* The pipeline continues normally to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | Tool guards `outfit` for None/empty/whitespace and returns a descriptive string instead of raising: *"I can't write a fit card without an outfit idea — try searching again or pick a different piece."* If instead the LLM call fails mid-generation, it returns a plain caption assembled from the item's title, price, and platform so the user still gets a shareable result. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     Use ASCII art or a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html).
     Do NOT embed an image — graders need to read your diagram directly in the file;
     an embedded image or screenshot cannot be evaluated.
     You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
                                  +------------------------------------------------------------+
                                  |                    SESSION STATE (dict)                    |
                                  |  query . parsed . search_results . selected_item .         |
                                  |  wardrobe . outfit_suggestion . fit_card . error           |
                                  +------------------------------------------------------------+
                                       ^ write/read at every stage (single source of truth)
                                       |
   +----------+  query + wardrobe  +---+--------------------------------------------------------+
   |   USER   | -----------------> |                  PLANNING LOOP (run_agent)                 |
   | (Gradio) |                    |                                                            |
   +----------+                    |  1. _new_session(query, wardrobe)                          |
        ^                          |  2. parse query -> parsed{description, size, max_price}    |
        |                          +---+--------------------------------------------------------+
        |                              | description, size, max_price
        |                              v
        |                     +-------------------+
        |                     |  search_listings  |  (pure Python over listings.json)
        |                     +---------+---------+
        |            list[dict] results |
        |                               v
        |                      +-------------------+
        |                      |  results empty?   |
        |                      +------+------+-----+
        |            YES (error branch)|      | NO
        |   +--------------------------+      | selected_item = results[0]
        |   v                                 v
        | +-------------------------+   +------------------+  selected_item + wardrobe
        | | set session["error"]    |   |  suggest_outfit  | <-- reads wardrobe from state
        | | (no-results message)    |   +--------+---------+     (empty wardrobe -> general advice)
        | | return session EARLY    |            | outfit_suggestion (str)
        | +-----------+-------------+            v
        |             |                  +------------------+  outfit + selected_item
        |             |                  |  create_fit_card |     (empty outfit -> guarded msg)
        |             |                  +--------+---------+
        |             |                           | fit_card (str)
        |             |                           v
        |             |                  +------------------+
        +-------------+------------------|  return session  |-- listing + outfit + fit_card
          error text in panel 1         +------------------+    to UI (3 panels)
          (panels 2 & 3 empty)
```

Legend: arrows show data passed between components; the "results empty?" box is the conditional branch after `search_listings`; the left-hand path is the **error branch** where the flow terminates early with only `session["error"]` set; the right-hand path is the happy pipeline. Every tool reads from and writes to SESSION STATE (top box).

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use claude one tool at a time so each can be tested in isolation before the next. I will give it the exact section for that tool from this planning.md, the function's existing docstring + signature in `tools.py`, and the data shapes from `utils/data_loader.py` (`load_listings()` fields) and `data/wardrobe_schema.json`. From this, I want to get a single complete function body matching the signature — `search_listings` as pure Python keyword-overlap scoring (no LLM), `suggest_outfit` and `create_fit_card` as Groq LLM calls via the `_get_groq_client()` helper, each with the documented failure handling. To factcheck, I'll run `python -c` snippets / a small `pytest` against each. 
For example, `search_listings`: confirm `"vintage graphic tee", max_price=30` returns non-empty tee results, `"designer ballgown", "XXS", 5` returns `[]`, and results are price/size-filtered and score-sorted. `suggest_outfit`: confirm a populated wardrobe names real pieces (e.g. "Chunky white sneakers") and an empty wardrobe still returns a non-empty general-advice string. `create_fit_card`: confirm it mentions title/price/platform once each, varies across runs, and returns the guard string when `outfit=""`. Only after these pass do I move on.

**Milestone 4 — Planning loop and state management:**
I'll use Claude again, this time feeding it the **Planning Loop**, **State Management**, and **Architecture diagram** sections above plus the `run_agent`/`_new_session` scaffolding in `agent.py`. I want it to then implement `run_agent()` with the 6-step pipeline with the early-exit case after `search_listings`, writing each result into the exact session keys named in State Management, plus the query-parsing step. Then, It should implement `handle_query()` in `app.py` mapping the session to the three panels.
I'll verify this by running the CLI block in `agent.py`. The optimal path query would populate `selected_item`/`outfit_suggestion`/`fit_card` with `error is None`. An unoptimal path with a query like "designer ballgown size XXS under $5"  would return early with `error` set and the other fields `None`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

When the user asks for an item or style, the agent first calls search_listings to filter the catalog by the requirements. Then it will call suggest_outfit to pair a listing against their wardrobe and proceedingly it will call create_fit_card t make a final shoping reccomendation. If a tool fails, such as no lisitngs or empty wardrobe, etc. the agent would degrade by returning an empty result with a message stating what happened instead of crashing. 

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** Parse + search.
<!-- What does the agent do first? Which tool is called? With what input? -->
`run_agent()` builds a fresh session and parses the query into `parsed = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}` (no explicit size token in the query). It calls `search_listings("vintage graphic tee", None, 30.0)`. The tool drops anything over $30, scores the rest on keyword overlap with title/description/style_tags, and returns a non-empty list sorted best-first — the top hit is `lst_002` *"Y2K Baby Tee — Butterfly Print"* (`price 18.0`, `platform "depop"`, tags include `graphic tee`, `vintage`). The list is stored in `session["search_results"]`.

**Step 2:** Branch + select.
<!-- What happens next? What was returned from step 1? What tool is called now? -->
The loop checks `search_results`. It is non-empty, so it takes Branch B: `session["selected_item"] = search_results[0]` (the Y2K Baby Tee). No error is set. (Had the list been empty, it would instead set `session["error"]` and return here.) It then calls `suggest_outfit(selected_item, wardrobe)` with the example wardrobe (which contains baggy straight-leg jeans and chunky white sneakers — matching the user's stated style).

**Step 3:** Suggest outfit, then create fit card.
<!-- Continue until the full interaction is complete -->
`suggest_outfit` returns something like: *"Tuck the Y2K butterfly baby tee into your Baggy straight-leg jeans, throw on the Vintage black denim jacket, and finish with your Chunky white sneakers for an easy Y2K-streetwear look."* — stored in `session["outfit_suggestion"]`. The loop then calls `create_fit_card(outfit_suggestion, selected_item)`, which (at higher temperature) returns a 2–4 sentence caption mentioning the title, `$18`, and `depop` once each, e.g.: *"butterfly-print baby tee summer ✨ thrifted this Y2K gem on depop for $18 and paired it with my baggiest jeans + chunky sneakers. early 2000s but make it now. #thrifted #ootd"* — stored in `session["fit_card"]`. The loop returns the session.

**Final output to user:**
<!-- What does the user actually see at the end? -->
`handle_query()` sees `session["error"] is None` and fills the three Gradio panels:
- **🛍️ Top listing found:** formatted details of the Y2K Baby Tee — title, $18.00, condition "excellent", size "S/M", platform "depop", colors, brand.
- **👗 Outfit idea:** the outfit suggestion string from Step 3.
- **✨ Your fit card:** the shareable caption from Step 3.
