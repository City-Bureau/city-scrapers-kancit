# PR #6 Code Review: City of Kansas City Missouri Legistar Spiders

**Author:** 1992tw (Tammam Alwafai), with refactor by msrezaie
**Branch:** `kancit_missouricity_branch` → `main`
**Files:** 8 changed (+6,606, -6)

---

## Summary

Adds a mixin + spider factory to scrape 199 Kansas City, Missouri agencies from their Legistar calendar at `https://clerk.kcmo.gov/Calendar.aspx`. Overrides `_parse_legistar_events()` to target the calendar table only (skipping `gridUpcomingMeetings` to avoid duplicates) and filters events by exact agency name match.

| File | Purpose |
|------|---------|
| `city_scrapers/mixins/kancit_missouricity.py` | `KancitMissouricityMixin` base class (169 lines) |
| `city_scrapers/spiders/kancit_missouricity.py` | Factory creating 199 spider classes (1,863 lines) |
| `tests/test_kancit_missouricity.py` | 15 tests (all pass) |
| `tests/files/kancit_council.json` | Fabricated JSON fixture (3 meetings) |
| `tests/files/kancit_missouricity.html` | HTML fixture (4,276 lines — **unused**) |
| `run_all_spiders.py` | Utility script to run all spiders in parallel |
| `city_scrapers/mixins/__init__.py` | Empty init for package |
| `Pipfile.lock` | Scrapy bump 2.11.2 → 2.14.1 |

### Spiders Created (sample of 199)

| Spider Name | Agency | Classification |
|-------------|--------|----------------|
| `kancit_001` | 1200 Main South Loop Community Improvement District | NOT_CLASSIFIED |
| `kancit_024` | City Council Business Session | CITY_COUNCIL |
| `kancit_027` | City Plan Commission | COMMISSION |
| `kancit_034` | Council | CITY_COUNCIL |
| `kancit_199` | Youth Development Committee | COMMITTEE |

---

## Code Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                      MODULE LOAD                                      │
├──────────────────────────────────────────────────────────────────────┤
│  kancit_missouricity.py                                               │
│    └── create_spiders() called at import                              │
│          └── For each of 199 configs:                                 │
│                type(class_name, (KancitMissouricityMixin,), attrs)    │
│                globals()[class_name] = spider_class                   │
│          └── KancitMissouricityMixinMeta.__init__() validates attrs   │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     SPIDER EXECUTION                                  │
├──────────────────────────────────────────────────────────────────────┤
│  1. LegistarSpider.start_requests()                                   │
│       └── GET https://clerk.kcmo.gov/Calendar.aspx                   │
│                                                                       │
│  2. LegistarSpider.parse(response)                                    │
│       └── _parse_secrets() → extract VIEWSTATE, EVENTVALIDATION      │
│       └── For each year 2020..current_year:                           │
│             POST with year selector → _parse_legistar_events_page    │
│                                                                       │
│  3. _parse_legistar_events_page(response)                             │
│       ├── OVERRIDDEN _parse_legistar_events(response)                │
│       │     └── CSS: table.rgMasterTable[id*='gridCalendar']         │
│       │     └── Parse headers, extract rows, detect links            │
│       │     └── Deduplicate by iCalendar URL (_scraped_urls set)     │
│       ├── parse_legistar(events) [MIXIN METHOD]                      │
│       │     └── Filter by agency name (exact match)                  │
│       │     └── legistar_start() → parse datetime                    │
│       │     └── Create Meeting with hardcoded location               │
│       │     └── legistar_links() / legistar_source()                 │
│       │     └── _get_status(text=location_text)                      │
│       └── _parse_next_page() → pagination via POST                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Must Fix

### 1. BUG: 12 duplicate IDs in live output

**`kancit_missouricity.py` (via mixin)** — Live crawl of `kancit_034` produces **267 items but only 255 unique IDs**. The iCalendar URL dedup in `_parse_legistar_events` doesn't prevent cross-year duplicates — the same meeting appears on different year pages with different iCalendar URLs.

```
kancit_034/202012031500/x/council  (2x)
kancit_034/202102111500/x/council  (3x)
kancit_034/202202141500/x/council  (3x)
...and 7 more
```

**Fix:** Add secondary dedup on generated ID in `parse_legistar`:
```python
def parse_legistar(self, events):
    seen_ids = set()
    for event in events:
        if not self._is_agency_match(event):
            continue
        start = self.legistar_start(event)
        if not start:
            continue
        # ... create meeting ...
        meeting["id"] = self._get_id(meeting)
        if meeting["id"] in seen_ids:
            continue
        seen_ids.add(meeting["id"])
        yield meeting
```

---

### 2. BUG: Duplicate `"agency"` in metaclass validation

**`kancit_missouricity.py:14`** — `required_static_vars` has `"agency"` twice:

```python
required_static_vars = ["agency", "name", "agency"]  # "agency" duplicated
```

Also, this validation is effectively a no-op — the factory always passes `name` and `agency` as keys in `attrs`, so the `if var not in dct` check can never fail. The `wycokck.py` mixin uses `__init_subclass__` + `getattr(cls, var, None) is None` which actually validates the *value* isn't `None`.

**Fix:** Either align with the `wycokck.py` pattern or remove the metaclass entirely:
```python
# Option A: fix the list
required_static_vars = ["agency", "name", "classification"]

# Option B: align with wycokck.py — use __init_subclass__ instead of metaclass
def __init_subclass__(cls, **kwargs):
    super().__init_subclass__(**kwargs)
    for var in ["name", "agency", "classification"]:
        if getattr(cls, var, None) is None:
            raise NotImplementedError(...)
```

---

### 3. Silent `except Exception: pass` in HTML parsing

**`kancit_missouricity.py:116-117`** — Row parsing errors are silently swallowed:

```python
except Exception:
    pass
```

Same pattern flagged in PR #10 (Must Fix #3). If the Legistar page structure changes, rows would silently fail with no indication.

**Fix:** Log the error:
```python
except Exception as e:
    self.logger.warning("Error parsing calendar row: %s", e)
```

---

### 4. Test fixture uses fabricated data that doesn't match live site

**`tests/files/kancit_council.json`** — Fixture uses `MeetingDetail.aspx` URLs:
```json
"Name": {"label": "Council", "url": "https://clerk.kcmo.gov/MeetingDetail.aspx?ID=1001"}
```

Live site returns `DepartmentDetail.aspx` for **all** 267 items:
```
https://clerk.kcmo.gov/DepartmentDetail.aspx?ID=43595&GUID=...
```

The tests validate against data that never occurs in production. Same issue flagged in PR #7 (Should Fix #10).

**Fix:** Capture real response data from a live crawl to use as the fixture.

---

### 5. `_parse_legistar_events` (most complex code) has zero test coverage

**`test_kancit_missouricity.py`** — Tests only exercise `parse_legistar()` with pre-parsed JSON. The overridden `_parse_legistar_events()` — which handles HTML table parsing, header extraction, URL detection, iCalendar dedup — is untested.

The unused `kancit_missouricity.html` fixture (4,276 lines loaded into `test_html` but never referenced) suggests this test was planned but never implemented.

**Fix:** Either implement the HTML parsing test using the existing fixture, or remove the unused fixture and `test_html` variable.

---

### 6. PR description references non-existent spider name

PR body says:
```
scrapy crawl kancit_council -O test_output.json
```
No spider named `kancit_council` exists. The Council spider is `kancit_034`.

---

## Should Fix

### 7. Typo: "attachement" → "attachment" (199 occurrences)

**`kancit_missouricity.py`** — Nearly every spider description contains "attachement" (missing 't'). Appears ~199 times across all configs.

**Fix:** Find and replace, or better yet, extract into a constant:
```python
DESC_VIRTUAL = (
    "{agency} meetings are also held virtually. "
    "Please check the meeting attachment for details on how to attend."
)
DESC_DEFAULT = "Please check the meeting attachment for details on how to attend."
```

---

### 8. `iCalendar` detection differs from parent class

**`kancit_missouricity.py:100`** — The mixin drops the header check that the parent has:

```python
# Mixin (no header check):
if "View.ashx?M=IC" in url:

# Parent LegistarSpider:
if header in ["", "ics"] and "View.ashx?M=IC" in url:
```

If a named column happened to contain a `View.ashx?M=IC` URL, it would be incorrectly labeled as iCalendar. Unlikely but easy to align with the parent.

---

### 9. All 199 spiders hit the same URL across all years

Each spider GETs `Calendar.aspx` + POSTs for each year (2020–2026). Running all 199 = ~1,400+ requests to the same server. Combined with `ROBOTSTXT_OBEY: False` and `run_all_spiders.py` setting `DOWNLOAD_DELAY=0` + `CONCURRENT_REQUESTS=16`, this risks overwhelming or getting blocked by the server.

---

## Nits

### 10. Non-descriptive spider names

Spider names `kancit_001` through `kancit_199` are opaque compared to the project convention (`kancit_board_commissioners`, `kancit_board_of_directors`). Makes log output and debugging harder.

### 11. Inconsistent `meeting_location` dict formatting

Some configs use multi-line dicts, others use inline `{"name": "", "address": ""}`. Cosmetic.

### 12. `# noqa` on most description lines

Nearly every config has `# noqa` for line length. Extracting descriptions into constants (see Should Fix #7) would eliminate these.

---

## Live Crawl Results

```
Spider:     kancit_034 (Council)
Items:      267 total, 255 unique IDs (12 duplicates)
Date range: 2020-01-02 to 2026-03-12
Status:     266 passed, 1 tentative
With links: 174 (65%), without: 93 (35%)
Sources:    100% DepartmentDetail.aspx (0% MeetingDetail.aspx)
Location:   100% hardcoded City Hall address (as designed)
```

---

## Verdict

**Request changes.** The architecture (mixin + factory) is solid and the approach to Legistar's dual-table layout is thoughtful. But there are data quality bugs and testing gaps that should be addressed.

| # | Issue | Severity | Type |
|---|-------|----------|------|
| 1 | Duplicate IDs (12 in live crawl) | Must fix | Bug |
| 2 | Duplicate "agency" in metaclass / no-op validation | Must fix | Bug |
| 3 | Silent `except Exception: pass` | Must fix | Reliability |
| 4 | Fabricated test fixture doesn't match live data | Must fix | Test quality |
| 5 | `_parse_legistar_events` untested + unused HTML fixture | Must fix | Test coverage |
| 6 | PR description wrong spider name | Must fix | Documentation |
| 7 | "attachement" typo x199 | Should fix | Data quality |
| 8 | iCalendar detection diverges from parent | Should fix | Correctness |
| 9 | 199 spiders x 7 years = 1,400+ requests | Should fix | Performance |
| 10 | Non-descriptive spider names | Nit | Convention |
| 11 | Inconsistent dict formatting | Nit | Style |
| 12 | `# noqa` on most lines | Nit | Style |

---

## Kind Comments

### Comment 1 — Must Fix #1: Duplicate IDs in live output

> Really nice work on the iCalendar URL dedup in `_parse_legistar_events` — that's a smart way to handle Legistar's dual-table layout! I ran the spider live and it mostly works great, but I noticed 12 duplicate IDs where the same meeting appears across different year pages with different iCalendar URLs (267 items, 255 unique).
>
> Would you mind adding a secondary dedup on the generated meeting ID in `parse_legistar`? Something like:
> ```python
> seen_ids = set()
> # ... inside the loop after _get_id():
> if meeting["id"] in seen_ids:
>     continue
> seen_ids.add(meeting["id"])
> ```
> That would catch the cross-year duplicates the URL dedup misses. Thanks!

### Comment 2 — Must Fix #2: Metaclass `required_static_vars`

> I like the idea of validating required attributes at class creation time — fail-fast is always good! I noticed `"agency"` appears twice in `required_static_vars` (line 14):
> ```python
> required_static_vars = ["agency", "name", "agency"]
> ```
> Also, since the factory always passes these as keys in `attrs`, the `if var not in dct` check can't actually fail. The `wycokck.py` mixin handles this differently with `__init_subclass__` + `getattr(cls, var, None) is None`, which validates the *value* isn't `None`. Would you consider aligning with that approach for consistency?

### Comment 3 — Must Fix #3: Silent exception handling

> The `except Exception: pass` on line 116-117 keeps the spider resilient, which is great — one bad row shouldn't kill the whole crawl. But silently dropping errors makes it really hard to debug when something changes on the Legistar page. Would you mind adding a log line?
> ```python
> except Exception as e:
>     self.logger.warning("Error parsing calendar row: %s", e)
> ```
> Same pattern came up in the Board of Directors review (PR #10) — having visibility into parsing failures saves a lot of debugging time in production.

### Comment 4 — Must Fix #4: Test fixture vs live data

> The test structure looks solid — good coverage of all the key fields! One thing I noticed when comparing with live output: the fixture uses `MeetingDetail.aspx` URLs, but the live site returns `DepartmentDetail.aspx` for all items. This means the `test_source` assertion passes against data that doesn't match production.
>
> Would you be able to capture a real response to use as the fixture? That way the tests would catch any URL pattern changes. Happy to help if you'd like — I saved a live crawl output that could work as a starting point.

### Comment 5 — Must Fix #5: HTML fixture loaded but unused

> I see `kancit_missouricity.html` (4,276 lines) is loaded into `test_html` on line 16-17 but never used in any test. It looks like there was a plan to test `_parse_legistar_events()` — the HTML parsing override is the most complex part of the mixin, so having test coverage would be really valuable.
>
> If you'd like to add that test, the fixture is already there! If not, removing the unused `test_html` variable and the HTML file would keep things clean. Either way works — just let me know your preference.

### Comment 6 — Must Fix #6: PR description spider name

> Quick heads-up — the PR description says `scrapy crawl kancit_council` but the actual spider name is `kancit_034`. Could you update the description so reviewers can test without hitting "spider not found"?

### Comment 7 — Should Fix: "attachement" typo

> Tiny typo that shows up everywhere — "attachement" should be "attachment" in the description strings. Since it appears in nearly all 199 configs, you could also extract the common text into constants:
> ```python
> DESC_VIRTUAL = (
>     "{agency} meetings are also held virtually. "
>     "Please check the meeting attachment for details on how to attend."
> )
> DESC_DEFAULT = "Please check the meeting attachment for details on how to attend."
> ```
> This would fix the typo in one place and clean up all the `# noqa` comments too!

### Comment 8 — Praise

> Great work overall! The factory pattern with `type()` + `create_spiders()` is clean and avoids 199 separate spider files. The mixin design is well-structured — `parse_legistar` filters by agency, and targeting `gridCalendar` specifically to avoid the `gridUpcomingMeetings` duplicates shows good understanding of how Legistar works. The status detection using location text is also a nice touch since Legistar often puts cancellation info there. Solid foundation for covering all 199 KC agencies!
