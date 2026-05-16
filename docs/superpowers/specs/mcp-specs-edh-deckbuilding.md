# MCP Server Specs for Commander Deckbuilding

Four servers to complement an existing Scryfall MCP. Each section lists the server's purpose, data source, and exposed tools with input/output shapes and implementation notes.

---

## 1. EDHREC MCP Server

**Purpose:** Surface community deckbuilding data — what cards actually get played with a given commander, synergy scores, popular themes, and budget alternatives.

**Data source:** EDHREC's JSON endpoints (e.g., `https://edhrec.com/api/commanders/{slug}.json`). Unofficial but stable. Respect rate limits and cache aggressively.

### Tools

#### `get_commander_recommendations`
- **Input:**
  - `commander_name` (string, required)
  - `theme` (string, optional — e.g., `"tokens"`, `"voltron"`, `"party"`)
  - `budget` (enum, optional — `"budget"` | `"expensive"` | null)
- **Output:** Cards grouped by category (Creatures, Instants, Sorceries, Artifacts, Enchantments, Planeswalkers, Lands, Utility Lands) with per-card fields:
  - `name`
  - `inclusion_percent` — % of decks with this commander running the card
  - `synergy_score` — delta between inclusion rate in this commander vs. general base rate
  - `num_decks`
  - `price_usd`
- **Notes:** Synergy score is the key signal. A card with 90% inclusion but +2% synergy is generic staple; 40% inclusion with +35% synergy is commander-specific. Weight synergy over raw inclusion when suggesting signal cards.

#### `get_commander_themes`
- **Input:** `commander_name` (string)
- **Output:** List of `{theme_name, deck_count, slug}`
- **Notes:** Each theme has its own recommendation page with a different card pool. Feed the slug back into `get_commander_recommendations`.

#### `get_card_top_commanders`
- **Input:** `card_name` (string)
- **Output:** List of commanders that run this card most frequently, with inclusion percent
- **Notes:** Reverse lookup — useful for "what commanders want this card?" questions.

#### `get_average_deck`
- **Input:** `commander_name`, `theme` (optional)
- **Output:** A 99-card statistical average decklist
- **Notes:** Baseline for comparison — "what does a generic version of this deck look like?"

#### `get_budget_alternatives`
- **Input:** `card_name` (string), `max_price_usd` (number, optional)
- **Output:** Functionally similar cheaper cards from EDHREC's similarity data
- **Notes:** Combine with Scryfall pricing for freshness.

---

## 2. Commander Spellbook MCP Server

**Purpose:** Query the combo database — find combos by component cards, colors, or result; detect combos already present in a decklist.

**Data source:** Commander Spellbook's official API (`https://backend.commanderspellbook.com/`). Well-documented, stable.

### Tools

#### `find_combos_with_card`
- **Input:** `card_name` (string)
- **Output:** List of combos containing this card, each with:
  - `id`
  - `pieces` — list of card names
  - `color_identity` — WUBRG string
  - `prerequisites` — setup required
  - `steps` — how it executes
  - `results` — infinite mana, infinite damage, win the game, etc.

#### `find_combos_in_colors`
- **Input:**
  - `color_identity` (string, e.g., `"WUB"`)
  - `max_pieces` (int, optional)
  - `results_include` (string, optional, e.g., `"infinite mana"`)
  - `max_price_usd` (number, optional)
- **Output:** Combos legal in the given color identity, filtered by constraints.
- **Notes:** Core tool for commander-filtered combo discovery.

#### `find_combos_in_decklist`
- **Input:** `card_names` (list of strings)
- **Output:** Combos where *all* pieces exist in the provided list
- **Notes:** Highest-value tool — detects accidental or forgotten combos. Always run this when a user shares a decklist.

#### `find_near_misses`
- **Input:**
  - `card_names` (list)
  - `missing_max` (int, default 1) — how many pieces the deck can be short
  - `color_identity` (string, optional — filter to commander's colors)
- **Output:** Combos where the deck has all but N pieces
- **Notes:** Powers suggestions like "adding X completes a two-card combo with cards already in your deck."

#### `get_combo_details`
- **Input:** `combo_id`
- **Output:** Full combo record with steps, prerequisites, results, notes.

---

## 3. Rulings & Oracle MCP Server

**Purpose:** Answer rules interactions, keyword definitions, and layered ability questions that go beyond single-card oracle text.

**Data source:**
- Magic Comprehensive Rules (plaintext, published by WotC each set release)
- Scryfall rulings endpoint (duplicated here for consolidation, or omit if Scryfall MCP remains primary)
- Derived keyword glossary

### Tools

#### `search_comprehensive_rules`
- **Input:** `query` (string), `section` (string, optional — e.g., `"6"`, `"601"`)
- **Output:** Matching rule numbers with text, ranked by relevance.

#### `get_rule`
- **Input:** `rule_number` (string, e.g., `"702.19a"`)
- **Output:** Rule text plus parent/child rule references for context.

#### `get_keyword_definition`
- **Input:** `keyword` (string, e.g., `"myriad"`, `"cascade"`, `"party"`)
- **Output:**
  - `formal_definition` — CR text
  - `reminder_text` — card-text version
  - `related_rules` — CR section references
- **Notes:** Covers both evergreen and set-specific keywords.

#### `get_card_rulings`
- **Input:** `card_name` (string)
- **Output:** Official rulings attached to the card with dates.
- **Notes:** Overlaps with Scryfall. Keep if you want this server self-contained.

#### `explain_interaction`
- **Input:**
  - `card_a` (string)
  - `card_b` (string)
  - `scenario` (string, optional — describes the specific interaction)
- **Output:** Assembled context bundle — both cards' oracle text, relevant rules sections, applicable rulings. **Does not itself answer** — returns what the LLM needs to reason.
- **Notes:** Most interaction questions are layering/timing/replacement-effect problems. This tool's job is to pull the right rules text into context so the model can reason correctly rather than hallucinate.

---

## 4. Deck Analytics MCP Server

**Purpose:** Run statistical and probabilistic analysis on decklists — mana curve, color requirements, draw probabilities, category balance, land count.

**Data source:** Computed locally from decklist input plus Scryfall data (card CMC, mana cost, type line, oracle text). Bundle a daily Scryfall data dump or call the Scryfall MCP as a sibling.

### Tools

#### `analyze_mana_curve`
- **Input:** `decklist` (list of card names, or Moxfield/Archidekt/EDHREC URL)
- **Output:**
  - CMC distribution (0, 1, 2, ... 7+)
  - Average CMC
  - Average CMC excluding lands and ramp
  - Histogram-ready data

#### `analyze_color_requirements`
- **Input:** `decklist`
- **Output:**
  - Pip count per color (total colored mana symbols in costs)
  - Required sources per color (Karsten model: ~12 sources per single-pip card, ~18 for double-pip)
  - Current source count per color
  - Deficit or surplus per color
- **Notes:** Flags mana base problems directly — "you want 18 W sources, you have 14."

#### `hypergeometric_probability`
- **Input:**
  - `deck_size` (int, default 99)
  - `successes_in_deck` (int)
  - `sample_size` (int, default 7)
  - `min_successes` (int, default 1)
- **Output:** Probability of drawing at least N copies.
- **Notes:** Classic calculator. Useful for "chance to see a ramp piece in my opening hand" or "chance to draw a combo piece by turn 5."

#### `categorize_deck`
- **Input:** `decklist`
- **Output:** Count and membership list per category — Ramp, Card Draw, Targeted Removal, Board Wipes, Protection, Tutors, Win Conditions, Utility Lands, Lands, Creatures (non-utility), Other.
- **Notes:** Requires tagging logic. Options: use EDHREC's card tags, heuristics on oracle text, or a bundled tag file. Rule-of-thumb Commander targets — ~10 ramp, ~10 draw, ~8 removal, ~3 wipes, ~36 lands — can be returned alongside for comparison.

#### `suggest_land_count`
- **Input:** Either `decklist` or `{avg_cmc, ramp_count, draw_count}`
- **Output:** Recommended land count with reasoning
- **Notes:** Base on Frank Karsten's Commander-adjusted formula. Account for MDFC lands and cheap ramp as fractional lands.

#### `goldfish_opening_hands`
- **Input:**
  - `decklist`
  - `num_hands` (int, default 1000)
  - `mulligan_rule` (string, optional — `"london"` default)
- **Output:** Statistics over N simulated opening hands — keepable-hand rate, average lands in keep, colors present, ramp-present rate.
- **Notes:** Monte Carlo. More expensive than other tools; consider a separate endpoint or a `fast_mode` that skips mulligan logic.

---

## Integration Notes

- **Card name normalization:** All tools accept case-insensitive names, handle split/DFC cards with `//`, and tolerate punctuation (apostrophes, commas). Return canonical Scryfall name in outputs.
- **Decklist input formats:** Accept raw text (newline-separated, with or without quantities and set codes) and Moxfield/Archidekt/EDHREC deck URLs.
- **Color identity:** Use WUBRG ordering in all strings.
- **Output format:** Prefer structured JSON over prose — the model can format.
- **Caching:** EDHREC and Commander Spellbook data changes slowly (hourly-daily refresh is fine). Rules data updates per set release. Cache aggressively.
- **Cross-server calls:** Deck Analytics benefits from having card data on hand. Either bundle a Scryfall data dump or allow it to call a sibling Scryfall MCP.

---

## Priority Order for Implementation

1. **EDHREC** — biggest leverage on "what am I missing" questions
2. **Commander Spellbook** — `find_combos_in_decklist` alone is worth the build
3. **Deck Analytics** — `categorize_deck` and `analyze_color_requirements` are the high-value tools
4. **Rulings/Oracle** — mostly backstop for thorny interactions; lowest per-query frequency
