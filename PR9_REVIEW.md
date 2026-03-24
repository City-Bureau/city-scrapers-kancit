# PR #9 Code Review: Add kancit_kckps_boe spider for KCKPS Board of Education

**Author:** DoinaFitchevici (Doina Fitchevici)
**Branch:** `kancit_kckps_boe`
**Files:** `city_scrapers/spiders/kancit_kckpsboe.py`, `tests/test_kancit_kckpsboe.py`, `tests/files/kancit_kckpsboe.json`

## Summary

Adds a spider for the Kansas City Kansas Public Schools Board of Education. Scrapes from a JSON API at `kckps.community.highbond.com`. Handles title normalization (removing dates, times, "- Current" suffix), hardcoded location mapping by meeting type, and default start times for meetings where the API returns midnight.

| Spider Name | Agency |
|-------------|--------|
| `kancit_kckps_boe` | Kansas City Kansas Public Schools Board of Education |

## Code Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     SPIDER EXECUTION                             │
├─────────────────────────────────────────────────────────────────┤
│  1. start_requests()                                            │
│       └── Build URL: from=2014-07-01, to=today+365d             │
│       └── Cache buster via datetime.utcnow() timestamp          │
│       └── Single request to meetings API                        │
│                                                                 │
│  2. parse(response)                                             │
│       └── response.json() → list of meetings                    │
│       └── For each item → _create_meeting()                     │
│             └── _parse_title()          → Remove dates/times    │
│             └── _parse_classification() → COMMITTEE or BOARD    │
│             └── _parse_start()          → Midnight defaults     │
│             └── _parse_time_notes()     → Always adds note      │
│             └── _parse_location()       → LOCATION_MAP lookup   │
│             └── _parse_links()          → Meeting detail URL    │
└─────────────────────────────────────────────────────────────────┘
```

## Issues Found

### Must Fix

1. **`datetime.utcnow()` is deprecated in Python 3.12** (`kancit_kckpsboe.py:34`)
   ```python
   "_": int(datetime.utcnow().timestamp() * 1000),  # cache buster
   ```
   This raises a `DeprecationWarning` and is scheduled for removal. Since this is just a cache buster, use:
   ```python
   "_": int(datetime.now().timestamp() * 1000),
   ```
   Or `datetime.now(timezone.utc)` if UTC is actually needed.

2. **`ROBOTSTXT_OBEY: False` without justification** (`kancit_kckpsboe.py:19`)
   Disabling robots.txt compliance should have a comment explaining why (e.g., the API endpoint returns no useful robots.txt, or it incorrectly blocks the scraper). Not a blocker but should be documented.

### Nits / Suggestions

3. **LOCATION_MAP ordering matters but isn't documented** (`kancit_kckpsboe.py:143-198`)
   The location lookup iterates the list in order and returns the first match. "Special Board Meeting Agenda" must come before "Special" (and it does), but a comment noting this would prevent accidental reordering. Same for "Regular Board Meeting Agenda" before "Regular Meeting Agenda".

4. **`MIDNIGHT_DEFAULTS` uses dict with int keys** (`kancit_kckpsboe.py:121-135`)
   The dict maps hour → list of title keywords. The keyword `"Aug 1, 2014 (Fri)"` is very specific and looks like it handles a single historical meeting. Consider whether this level of specificity is worth maintaining.

5. **Title parsing has many regex passes** (`kancit_kckpsboe.py:79-109`)
   Three time patterns, then string replacement, then dash splitting, then four date patterns, then whitespace normalization. This works but is complex. The `rsplit(" - ", 1)` on line 94 is the primary mechanism — the date patterns after it are mostly cleanup for edge cases. A comment summarizing the strategy would help.

6. **Finance Committee has empty address** (`kancit_kckpsboe.py:157-161`)
   The Finance Committee location has `"address": ""` while other committees have the full address. Is this intentional (virtual meetings) or an oversight?

7. **`time_notes` always includes a generic note** (`kancit_kckpsboe.py:222`)
   Every meeting gets "Please check meeting attachments for accurate time and location." This is appropriate given most meetings have 00:00 start times in the API, but meetings with actual times (e.g., Finance Committee at 13:00) also get this note unnecessarily.

8. **Unused import: `date`** (`kancit_kckpsboe.py:2`)
   `date` is imported from `datetime` but only used in `start_requests()`. Actually it is used — `date.today()`. Disregard.

### Bug / Logic Issues

9. **`_parse_time_notes` misses Special meeting variants** (`kancit_kckpsboe.py:225-228`)
   The virtual meeting note condition only matches `"Special Meeting Agenda"` exactly:
   ```python
   if (
       "Finance Committee Meeting" in meeting_title
       or "Special Meeting Agenda" in meeting_title
   ):
   ```
   - `"Special Board Meeting Agenda"` — does NOT contain `"Special Meeting Agenda"` — **missed**
   - `"Special (Budget) Meeting Agenda"` — does NOT contain `"Special Meeting Agenda"` — **missed**
   - Only `"Special Meeting Agenda"` (fixture index 10) matches

   If all special meetings should get the virtual note, this should use a broader check, e.g. `"Special" in meeting_title`.

10. **Finance Committee name inconsistency** (`kancit_kckpsboe.py:160 vs 138`)
    The `CENTRAL_OFFICE` constant is `"Kansas Public Schools"`, but the Finance Committee entry hardcodes a different name:
    ```python
    # Line 138
    CENTRAL_OFFICE = "Kansas Public Schools"

    # Line 160 - Finance Committee
    "name": "Kansas City, Kansas Public Schools",  # different!
    ```
    This looks unintentional. Either Finance Committee should use `CENTRAL_OFFICE`, or this is a deliberate distinction that needs a comment.

### Redundancies

11. **Boilerplate docstring left in `parse()`** (`kancit_kckpsboe.py:40-44`)
    ```python
    def parse(self, response):
        """
        `parse` should always `yield` Meeting items.

        Change the `_parse_title`, `_parse_start`, etc methods to fit your scraping
        needs.
        """
    ```
    This is the template docstring from the scaffold. Should be replaced with an actual description.

12. **`_get_raw_title()` called 5 times per item** (`kancit_kckpsboe.py:50-68`)
    `_create_meeting` triggers `_parse_title`, `_parse_classification`, `_parse_start`, `_parse_time_notes`, and `_parse_location`, each calling `_get_raw_title(item)` independently. Computing it once in `_create_meeting` and passing it through would be cleaner.

13. **Unused `# noqa` comments**
    - Spider: lines 99, 147, 230 — Ruff flags these as unnecessary (RUF100)
    - Tests: lines 21, 82, 108, 148 — same issue

### Optimization Opportunities

14. **Pre-compile regex patterns** (`kancit_kckpsboe.py:79-106`)
    The time and date patterns in `_parse_title` are recompiled via `re.sub()` on every call. For ~500 meetings, that's thousands of unnecessary recompilations. Pre-compiling them as class-level constants would improve performance:
    ```python
    TIME_PATTERNS = [
        re.compile(r"\s+at\s+\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)", re.IGNORECASE),
        ...
    ]
    ```

15. **Three time patterns could be one regex** (`kancit_kckpsboe.py:79-83`)
    ```python
    # Current: 3 separate patterns
    r"\s+at\s+\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)"  # "at 4:00 PM"
    r"\s+\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)"        # "4:00 PM"
    r"\s+\d{1,2}\s*(?:a\.?m\.?|p\.?m\.?)"               # "9 AM"

    # Could be combined into one:
    TIME_PATTERN = re.compile(
        r"\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)", re.IGNORECASE
    )
    ```

## Tests

Tests are well-structured using pytest fixtures with `freeze_time`. Good coverage across multiple meeting types (Academic Committee, Finance Committee, Facilities, Board Retreat, Boundary Committee, Regular Board, Special Board, Special Budget). 12 test fixtures with 30 test functions.

Minor: Test indices are hardcoded (e.g., `parsed_items[11]` for Special Budget). If fixture data order changes, tests break silently. Using a helper to find by title would be more robust.

### Test Gaps

16. **Items 9 and 10 are completely untested**
    - Index 9 (Regular Board Meeting Agenda 2025) — no assertions at all
    - Index 10 (Special Meeting Agenda) — no assertions at all

17. **Midnight default logic is barely tested**
    4 out of 5 midnight-default items have no start time assertions:

    | Index | Meeting | Midnight → Default | Tested? |
    |-------|---------|-------------------|---------|
    | 3 | Board Retreat | 14:00 | **No** |
    | 5 | Regular Board Meeting 2021 | 17:00 | Yes |
    | 6 | Regular Meeting Agenda | 17:00 | **No** |
    | 8 | Special Board Meeting | 13:00 | **No** |
    | 9 | Regular Board Meeting 2025 | 17:00 | **No** |

    The 14:00 (Board Retreat) and 13:00 (Special Board) defaults have **zero** test coverage.

18. **No test for Special Meeting virtual note** (index 10)
    Index 10 (`"Special Meeting Agenda"`) should produce a `time_notes` with the virtual meeting note appended, but there is no assertion for it.

19. **No test for location fallback**
    The fallback at line 244 (`{"address": "", "name": item.get("MeetingLocation", "")}`) is never exercised. All test items match a `LOCATION_MAP` entry. Adding a fixture item with an unrecognized meeting type would cover this path.

20. **Status only tested for 2 of 12 items**
    Only `"passed"` (index 0) and `"tentative"` (index 1) are tested. No coverage for edge cases or the `"cancelled"` status path.

## Verdict

**Approve with minor changes.** The `datetime.utcnow()` deprecation should be fixed (trivial one-line change). Issues #9 (time_notes logic) and #10 (name inconsistency) should be reviewed for correctness. Test gaps (#16-#20) are worth addressing to ensure the midnight-default and location-fallback logic is properly covered. The rest are nits. The spider correctly handles a complex API with varied meeting formats, and the overall structure is solid.
