# MTG MCP Server Refactor Spec
> Goal: reduce per-call token overhead by grouping tools into namespaces and trimming descriptions to single-line summaries. Merge redundant tools where logic overlaps.

---

## Server: `scryfall`

### Namespace: `scryfall.card`
| Tool | Signature hint | One-line summary |
|------|---------------|-----------------|
| `get` | `(name)` | Fetch a single card by exact name. |
| `get_by_set` | `(set_code, collector_number)` | Fetch a specific printing by set + collector number. |
| `get_bulk` | `(names[])` | Fetch multiple cards by name in one call. |
| `search` | `(query)` | Search cards using full Scryfall syntax. |
| `get_rulings` | `(name)` | Return official rulings for a card with dates. |
| `get_top_commanders` | `(name)` | List Commanders that most frequently run this card (EDHREC). |
| `get_budget_alternatives` | `(name)` | Find cheaper functionally similar cards via EDHREC. |

### Namespace: `scryfall.commander`
| Tool | Signature hint | One-line summary |
|------|---------------|-----------------|
| `get_recommendations` | `(commander, theme?)` | Get EDHREC card recommendations grouped by category. |
| `get_average_deck` | `(commander)` | Return the statistical 99-card average decklist from EDHREC. |
| `get_themes` | `(commander)` | List available strategies/themes for a Commander on EDHREC. |

> **Merge candidate:** `get_recommendations` + `get_average_deck` overlap heavily. Consider a single `scryfall.commander.get_edhrec(commander, mode: "recommendations" | "average_deck")`.

### Namespace: `scryfall.combo`
| Tool | Signature hint | One-line summary |
|------|---------------|-----------------|
| `find` | `(scope: "colors"\|"decklist"\|"near_miss", input, missing_max?)` | Find combos by color identity, decklist, or near-miss (merged). |
| `get_details` | `(combo_id)` | Get full steps, prerequisites, and results for a combo by ID. |

> **Merge:** `find_combos_in_colors`, `find_combos_in_decklist`, `find_near_misses` → single `find` with a `scope` param.

### Namespace: `scryfall.rules`
| Tool | Signature hint | One-line summary |
|------|---------------|-----------------|
| `get` | `(rule_number)` | Look up a Comprehensive Rules entry by number. |
| `search` | `(query)` | Full-text search of the Comprehensive Rules. |
| `get_keyword` | `(keyword)` | Return the CR definition for a keyword ability or action. |
| `explain_interaction` | `(card_a, card_b)` | Assemble oracle text, rulings, and CR sections for two cards. |
| `cache_status` | `()` | Return the timestamp of the cached rules (new — avoids blind refresh). |
| `refresh_cache` | `()` | Force a re-fetch of the Comprehensive Rules. |

### Namespace: `scryfall.moxfield`
| Tool | Signature hint | One-line summary |
|------|---------------|-----------------|
| `get_deck` | `(deck_id)` | Fetch a Moxfield deck by public ID. |
| `find_deck` | `(name_query)` | Find a user deck by fuzzy name match, returns ID + metadata (new — avoids get_user_decks → get_deck two-hop). |
| `get_user_decks` | `()` | List all decks for the authenticated Moxfield user. |
| `refresh_credentials` | `()` | Re-authenticate Moxfield session via browser login. |

---

## Server: `mtg_analytics`

### Namespace: `mtg_analytics.mana`
| Tool | Signature hint | One-line summary |
|------|---------------|-----------------|
| `analyze_curve` | `(decklist)` | Analyse the mana curve of a decklist. |
| `analyze_color_requirements` | `(decklist)` | Analyse pip requirements using Frank Karsten's model. |
| `suggest_land_count` | `(decklist)` | Recommend land count using Karsten's Commander formula. |

### Namespace: `mtg_analytics.deck`
| Tool | Signature hint | One-line summary |
|------|---------------|-----------------|
| `categorize` | `(decklist)` | Classify cards into functional roles (Ramp, Draw, Removal, Wipes, etc.). |
| `goldfish_opening_hands` | `(decklist, n)` | Simulate N opening hands; return avg lands, ramp presence, colour coverage. |
| `hypergeometric` | `(population, successes, sample, min_hits)` | Probability of drawing ≥ min_hits copies in a given sample. |

---

## Summary of Changes

| Change | Token impact |
|--------|-------------|
| Namespace grouping (model reads shorter scoped descriptions) | Medium ↓ |
| One-line summaries replacing verbose paragraphs | High ↓ |
| Merge 3 combo tools → 1 | Low ↓ |
| Merge 2 EDHREC tools → 1 | Low ↓ |
| Add `cache_status` tool | Avoids unnecessary `refresh_cache` calls |
| Add `find_deck` shortcut | Eliminates common two-hop call pattern |
| Flag `explain_interaction` N-card limitation | Future: support array of cards for combo checks |
