# PR #10 Code Review (Strict): Kansas City Board of Directors Spider

**Author:** akhhanna20 (Hanna Akhramchuk)
**Branch:** `kancit_board_of_directors` → `main`
**Files:** 4 changed (+3,305, -0)
**Reviewer:** msrezaie (approved 2026-02-16, requested lint fixes 2026-02-23)

---

## Summary

Adds a spider for the Kansas City (Missouri) Board of Directors / Board of Education. Uses two data sources: the Simbli eBoard API (primary, for all historical + upcoming meetings) and the KCPS calendar (secondary, for upcoming-only meetings not on Simbli). Includes extensive location normalization for various venue formats (Board of Education variations, virtual, hybrid, special venues) and deduplication between sources.

| File | Purpose |
|------|---------|
| `city_scrapers/spiders/kancit_board_of_directors.py` | Spider (542 lines) |
| `tests/test_kancit_board_of_directors.py` | 38 tests (all pass) |
| `tests/files/kancit_board_of_directors.html` | Calendar HTML fixture (2,192 lines) |
| `tests/files/kancit_board_of_directors.json` | Simbli API JSON fixture (3 meetings) |

## Code Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                      SPIDER EXECUTION                                │
├──────────────────────────────────────────────────────────────────────┤
│  1. start_requests() [FIXED — was async def start()]                  │
│       └── Yields Request to Simbli main page                        │
│                                                                      │
│  2. parse(response) — Simbli HTML page                               │
│       ├── Guard: if response < 10,000 chars → silent return          │
│       ├── Extract connection_string (var constr) via regex            │
│       ├── Extract security_token (var sToken) via regex               │
│       └── _fetch_meetings_page(0, constr, sToken) → POST to API      │
│                                                                      │
│  3. parse_api_response(response) — Simbli JSON API (50 per page)     │
│       ├── _extract_meetings_from_response() → tries 4 JSON keys      │
│       ├── If no meetings → yield from fetch_calendar_meetings()       │
│       ├── For each meeting → _parse_simbli_meeting():                 │
│       │     ├── _normalize_title() → strip dates, HTML entities       │
│       │     ├── _parse_start_time() → "MM/DD/YYYY - HH:MM AM/PM"     │
│       │     ├── _parse_location() → 124-line venue normalization      │
│       │     ├── _classify_meeting() → committee > board > NOT_CLASSIF │
│       │     └── Track upcoming dates in simbli_upcoming_dates set     │
│       └── Paginate → _fetch_meetings_page(next_offset, ...)          │
│             └── Last page (empty) → triggers calendar fetch           │
│                                                                      │
│  4. fetch_calendar_meetings() — KCPS Calendar AJAX                   │
│       ├── Request 6 months of calendar HTML data                     │
│       └── parse_calendar_response() → CSS selectors                  │
│             └── parse_calendar_meeting() per event                   │
│                   ├── Skip past dates                                │
│                   ├── Skip dates already in simbli_upcoming_dates     │
│                   ├── _parse_calendar_datetime() → ISO 8601 / attrs  │
│                   └── Simple location: Board of Ed or empty           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Must Fix

### 1. CRITICAL: `async def start()` incompatible with Scrapy 2.11.2 — FIXED

**`kancit_board_of_directors.py:44`** — **Fixed and pushed to staging (commit `228665a`)**

```python
async def start(self):
    """New async start method for Scrapy 2.13+"""
    yield scrapy.Request(url=self.main_url, callback=self.parse)
```

The project pins Scrapy to **2.11.2** (in `Pipfile`) because `city_scrapers_core`'s `AzureBlobFeedStorage` isn't compatible with newer Scrapy versions yet. Scrapy 2.11 calls `start_requests()` as the entry point, not `async def start()`. Since this spider doesn't define `start_requests()`, the inherited default looks for `start_urls` (which is empty) — **resulting in 0 requests, 0 items**.

**Verified locally (4 test cases):**

| # | Version | Requests | Items | Result |
|---|---------|----------|-------|--------|
| 1 | `async def start()` (original) | 0 | 0 | Scrapy 2.11.2 never calls it |
| 2 | `async def start()` + calendar fallback | 0 | 0 | `parse()` never reached |
| 3 | `def start_requests()` only | 1 | 0 | Request sent, Simbli blocked locally (Incapsula) |
| 4 | `def start_requests()` + calendar fallback | 7 | 8 | Calendar works as fallback |

**Verified on CI:** After pushing fix, CI crawl successfully scraped **50+ meetings** from Simbli (no Incapsula block from GitHub Actions IP).

The other two spiders (`kancit_kckpsboe` and `wycokck` mixin) both use `def start_requests(self)`.

**Fix applied:** `async def start(self)` → `def start_requests(self)` (38/38 tests pass, lint clean).

---

### 2. `parse()` silently returns nothing on blocked/short responses

**`kancit_board_of_directors.py:196-198`**

```python
if len(response.text) < 10000:
    return
```

When Simbli returns a bot-protection page (Incapsula/Imperva), a CAPTCHA, or any error page, the response will be short. The spider silently returns nothing — no warning, no error, no fallback to the calendar. The spider finishes with 0 items and appears successful.

This is especially concerning because:
- The spider sets a hardcoded browser User-Agent specifically to avoid bot detection (line 26)
- If that UA ever stops working, the spider silently breaks with no indication
- The calendar source (`fetch_calendar_meetings()`) is never tried as fallback

**Fix:** At minimum, log a warning. Ideally, fall back to calendar:
```python
if len(response.text) < 10000:
    self.logger.warning(
        "Short response (%d chars) — possible bot protection. "
        "Falling back to calendar.", len(response.text)
    )
    yield from self.fetch_calendar_meetings()
    return
```

---

### 3. Silent `except json.JSONDecodeError: pass`

**`kancit_board_of_directors.py:305-306`**

```python
except json.JSONDecodeError:
    pass
```

If the Simbli API returns non-JSON (HTML error page, 500 error, etc.), the exception is silently swallowed. The spider produces 0 items with no indication of why.

**Fix:** Log the error:
```python
except json.JSONDecodeError:
    self.logger.error("Failed to parse API response as JSON: %s", response.url)
```

---

### 4. Empty links for calendar meetings

**`kancit_board_of_directors.py:152`**

```python
links=[{"href": "", "title": ""}],
```

Calendar meetings get a link with empty `href` and empty `title`. This produces a broken/meaningless link in the output. The other spiders in this project use `links=[]` when there are no links (see `kancit_kckpsboe.py:_parse_links()` and the `wycokck` mixin).

**Fix:** Use `links=[]`.

---

## Should Fix

### 5. `time_notes` hardcodes a long generic string on every meeting

**`kancit_board_of_directors.py:343`**

```python
time_notes="Please refer to the meeting attachments for more accurate information about the meeting details, address and time",
```

This identical 100+ character string is set on every single meeting — both Simbli and calendar items. It doesn't provide meeting-specific information. For comparison:
- `kancit_kckpsboe` uses a dynamic `_parse_time_notes()` method that adds conditional notes (e.g., virtual meeting info)
- The `wycokck` mixin uses `time_notes=""`

**Suggestion:** Either use `""` (like other spiders), or only add notes when there's specific information (e.g., "Virtual meeting — check attachments for link").

---

### 6. `datetime.now()` used without timezone awareness

**`kancit_board_of_directors.py:61, 126, 318`**

Three separate calls to `datetime.now()`:
- Line 61: `today = datetime.now()` — calendar month calculation
- Line 126: `start.date() < datetime.now().date()` — skip past calendar events
- Line 318: `start.date() >= datetime.now().date()` — track upcoming Simbli dates for dedup

`datetime.now()` uses the **system's local timezone**. If the CI runner is in UTC (common for cloud CI), `datetime.now()` at 11 PM UTC on Jan 9 = Jan 9, but in America/Chicago it's already Jan 10. This affects which meetings are considered "past" vs "upcoming" and breaks the dedup between Simbli and calendar.

Gemini's review also flagged this. The base class `CityScrapersSpider` doesn't provide a `self.now` helper, but using a consistent timezone-aware approach would be more reliable.

---

### 7. Duplicate entry in `VIRTUAL_KEYWORDS`

**`kancit_board_of_directors.py:442, 444`**

```python
VIRTUAL_KEYWORDS = [
    "conference call",    # line 442
    "videoconference",
    "conference call",    # line 444 — duplicate
    ...
]
```

`"conference call"` appears twice.

---

## Nits

### 8. Commented-out code

**`kancit_board_of_directors.py:357`**

```python
# title = title.replace("&amp;", "&")
title = html.unescape(title)
```

The commented-out line is dead code since `html.unescape()` handles `&amp;` and all other HTML entities. Remove it.

---

### 9. Emoji in code comments

**`kancit_board_of_directors.py:466, 485, 492, 499`**

```python
# ✅ HYBRID (Board of Education + Virtual)
# ✅ Physical Board Only
# ✅ Virtual and Teams
```

The checkmark emojis are inconsistent with the rest of the codebase. Regular comments like `# Hybrid meeting` would be cleaner.

---

### 10. `test_calendar_locations` has a weak assertion

**`test_kancit_board_of_directors.py:114-117`**

```python
assert (
    "Board of Education" in jan_20_meetings[0]["location"]["name"]
    or "Seven Oaks" in jan_20_meetings[0]["location"]["name"]
)
```

This `or` assertion passes if **either** condition is true, making it hard to know which is actually expected. Pick one expected value or split into separate assertions.

---

### 11. Calendar fallback triggers at end of pagination — logic is correct but comments are misleading

**`kancit_board_of_directors.py:277-303`**

The pagination flow works correctly:
1. API page with meetings → process + fetch next page
2. Last API page (empty) → `not meetings` is True → triggers `fetch_calendar_meetings()`
3. Calendar meetings are fetched **after** all Simbli pages, so `simbli_upcoming_dates` is fully populated for dedup

This is good behavior! But the docstring says "If no meetings are found, it falls back to scraping the calendar" (line 282), which implies Simbli failed. In reality, calendar is **always** fetched after the last Simbli page. The docstring should reflect that calendar is a supplementary source, not a fallback.

---

## Tests

**Excellent test coverage** (460 lines, 38 tests, all passing). This is the strongest test suite of the three spiders in this project.

Strengths:
- Proper pytest fixtures with `freeze_time` (not module-level setup)
- Both data sources tested separately (calendar + API)
- 7 title normalization test cases including edge cases
- Cancelled/rescheduled parentheses removal
- HTML entity decoding
- Classification logic (board, committee, workshop) with multiple examples
- Location parsing (6 scenarios: Board of Ed, trailing chars, other venue, special address, virtual, hybrid)
- ISO datetime parsing
- General structure validation for all fields
- Status correctness (passed vs tentative)
- Date range validation

The test fixture data uses **real API response structure** (realistic meeting IDs, realistic address data). This is much better than fabricated fixtures.

**One gap:** Tests don't exercise `start()` / `start_requests()` at all. They test `parse_api_response` and `parse_calendar_response` directly, which is why the critical Scrapy version incompatibility (Must Fix #1) wasn't caught.

---

## Cross-Reference with msrezaie's Feedback

msrezaie's three review rounds addressed real issues that were fixed:

| msrezaie's Comment | Status |
|---------------------|--------|
| Normalize Board of Education addresses consistently | Fixed — TROOST_VARIATIONS + BOARD_ADDRESS constant |
| Virtual meetings should have empty address | Fixed — is_virtual → `{"name": "Virtual", "address": ""}` |
| `simbli_upcoming_dates` as class var vs instance var | Author said "Done" but current code uses `__init__` (which is actually correct — mutable class vars are a Python footgun) |
| Additional location cases (Troost Ave, McCownGordon, Truman Rd, TEAMS) | Fixed — special cases added |
| Use `TENTATIVE` constant in test assertions | Fixed |
| Double underscore `parse__simbli_meeting` → single underscore | Fixed |
| Lint fixes needed | Fixed in subsequent commits |

The location normalization work (124 lines) is thorough and handles the cases msrezaie identified. The code is complex but the complexity is justified by the messy real-world data.

---

## Live Crawl Results

### Before fix (original `async def start`)
```
Spider:     kancit_board_of_directors
Items:      0
Requests:   0
Reason:     Scrapy 2.11.2 doesn't call async def start()
```

### After fix (`def start_requests`) — CI staging crawl
```
Spider:     kancit_board_of_directors
Items:      50+ meetings scraped
Requests:   3 (1 GET Simbli page + 2 POST API pages, 50 items/page)
Status:     200 on all requests
Pagination: Working (2 API pages)
```

**Data quality observations from CI output:**
- Classification working: Board ("Regular Business Meeting", "Policy Monitoring Workshop", "Board Retreat") and Committee ("Finance Ad Hoc Committee", "Government Relations Ad Hoc Committee", "Policy Committee")
- Location normalization working: Board of Education with canonical address, plus off-site venues (Lincoln College Preparatory Academy, Holliday Montessori School, George Washington Carver School, CBIZ MHM)
- Cancelled meeting detected: "Policy Monitoring Workshop" 2025-02-12 → `status: 'cancelled'`
- Duplicate correctly dropped by AzureDiffPipeline: "Policy Monitoring Workshop" 2025-06-11
- Date range: 2025-01 through 2026-02
- Suspicious: "Bond Board Workshop" 2025-07-30 has start time **02:00 AM** — likely a data issue from the source

---

## Verdict

**Request changes** (mostly resolved). Must Fix #1 was the blocker — already fixed and pushed to staging (commit `228665a`), verified working on CI with 50+ items scraped. Remaining issues (#2-#4) should be addressed to prevent silent failures and clean up data quality.

| # | Issue | Severity | Type | Status |
|---|-------|----------|------|--------|
| 1 | `async def start()` → 0 items | Must fix | Blocker | **FIXED** (staging `228665a`) |
| 2 | Silent return on blocked response | Must fix | Reliability | Open |
| 3 | Silent `json.JSONDecodeError: pass` | Must fix | Reliability | Open |
| 4 | Empty links `{"href": "", "title": ""}` | Must fix | Data quality | Open |
| 5 | `time_notes` hardcoded generic string | Should fix | Data quality | Open |
| 6 | `datetime.now()` timezone-unaware | Should fix | Correctness | Open |
| 7 | Duplicate "conference call" in keywords | Should fix | Cleanup | Open |
| 8 | Commented-out code | Nit | Cleanup | Open |
| 9 | Emoji in comments | Nit | Style | Open |
| 10 | Weak `or` assertion in test | Nit | Test quality | Open |
| 11 | Misleading "fallback" docstring | Nit | Documentation | Open |

---

## Kind Comments

### Comment 1 — Must Fix #1: `async def start()` → `def start_requests()` — POSTED

> Hey @akhhanna20, great work on this spider! The dual-source approach and test coverage are impressive.
>
> One issue: `async def start(self)` on line 44 is a Scrapy 2.13+ feature, but the project pins Scrapy to 2.11.2 (because `city_scrapers_core`'s `AzureBlobFeedStorage` isn't compatible with newer versions yet). Scrapy 2.11 uses `start_requests()` instead, so the spider was producing 0 items.
>
> Fix — just change:
> ```python
> async def start(self):
> # to
> def start_requests(self):
> ```
>
> I've pushed this fix to staging and confirmed it works — 50+ meetings scraped successfully. The other spiders in this project both use `start_requests()` for reference.

### Comment 2 — Must Fix #2: Silent failure on short/blocked responses

> I noticed that when `parse()` gets a short response (< 10,000 chars), it silently returns nothing (line 196-198). This can happen when Simbli's bot protection kicks in — for example, Incapsula/Imperva pages are typically a few KB of HTML.
>
> Since you already have the calendar as a secondary source, this would be a great place to fall back to it:
> ```python
> if len(response.text) < 10000:
>     self.logger.warning(
>         "Short response (%d chars) — possible bot protection. "
>         "Falling back to calendar.", len(response.text)
>     )
>     yield from self.fetch_calendar_meetings()
>     return
> ```
>
> That way, even if Simbli blocks us, we'd still get upcoming meetings from the KCPS calendar.

### Comment 3 — Must Fix #3: Silent `json.JSONDecodeError`

> Small but important: the `except json.JSONDecodeError: pass` on line 305-306 silently swallows parsing errors. If the API ever returns non-JSON (like an HTML error page), the spider would produce 0 items with no indication of what went wrong. Adding a `self.logger.error(...)` here would make debugging much easier if this ever happens in production.

### Comment 4 — Must Fix #4: Empty links for calendar meetings

> For calendar meetings (line 152), the links are set to `[{"href": "", "title": ""}]`. This produces a link object with empty values in the output, which could confuse downstream consumers. The other spiders in this project use `links=[]` when there are no links available. Could you change this to `links=[]`?

### Comment 5 — Should Fix: `time_notes` generic string

> The `time_notes` field on line 343 has the same long message on every meeting:
> ```
> "Please refer to the meeting attachments for more accurate information..."
> ```
>
> Since this doesn't provide meeting-specific info, it adds noise to the data. For comparison, `kancit_kckpsboe` uses a dynamic approach that only adds notes when relevant (e.g., virtual meeting instructions). Would you consider either using `""` (like the wycokck mixin does) or only adding a note when there's something specific to say?

### Comment 6 — Should Fix: `datetime.now()` timezone

> I see `datetime.now()` used in three places (lines 61, 126, 318) for comparing dates. `datetime.now()` returns the system's local time, which could differ from America/Chicago on a CI runner. Since the spider sets `timezone = "America/Chicago"`, it might be worth using a timezone-aware approach for these date comparisons — especially for the Simbli/calendar dedup logic where a timezone mismatch could cause duplicate or missing meetings.

### Comment 7 — Nits: small cleanup items

> A few small nits:
> - `"conference call"` appears twice in `VIRTUAL_KEYWORDS` (lines 442 and 444)
> - The commented-out line on 357 (`# title = title.replace("&amp;", "&")`) can be removed since `html.unescape()` on the next line handles it

### Comment 8 — Praise for tests and location handling

> I want to call out how thorough the test suite is — 38 tests with proper pytest fixtures, `freeze_time`, and both data sources tested independently. This is the strongest test coverage of any spider in this project. The location normalization is also really well done; it handles all the messy real-world variations that msrezaie identified (Troost variations, virtual, hybrid, special venues). Nice work!
>
> One small suggestion: `test_calendar_locations` (line 114-117) uses an `or` in the assertion, which makes it pass if either condition is true. Picking a specific expected value would make the test more precise.
