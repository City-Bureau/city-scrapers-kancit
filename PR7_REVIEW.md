# PR #7 Code Review (Strict): Wyandotte County/Kansas City CivicClerk Spiders

**Author:** AmirhosseinOlyaei
**Branch:** `feature/kansascity-bocc` → `main`
**Files:** 6 changed (+670, -87)

---

## Summary

Adds a mixin + spider factory to scrape 7 Wyandotte County/Kansas City agencies from the CivicClerk API.

| File | Purpose |
|------|---------|
| `city_scrapers/mixins/__init__.py` | Empty init for package |
| `city_scrapers/mixins/wycokck.py` | `CivicClerkMixin` base class (241 lines) |
| `city_scrapers/spiders/kancit_wycokck.py` | Factory creating 7 spider classes (87 lines) |
| `tests/files/kancit_board_commissioners.json` | Fabricated fixture with 4 events |
| `tests/test_kancit_board_commissioners.py` | 17 tests (all pass) |
| `Pipfile.lock` | Dependency bumps |

### Spiders Created

| Spider Name | Agency | Category IDs |
|-------------|--------|-------------|
| `kancit_board_commissioners` | Board of Commissioners | 31, 33, 35, 36, 37 |
| `kancit_zoning_planning` | Zoning and Planning | 32 |
| `kancit_neighborhood_dev` | Neighborhood & Community Dev Standing Committee | 27 |
| `kancit_economic_dev` | Economic Dev & Finance Standing Committee | 28 |
| `kancit_public_works` | Public Works & Safety Standing Committee | 29 |
| `kancit_admin_human_services` | Admin & Human Services Standing Committee | 30 |
| `kancit_task_force` | Committee/Task Force | 34 |

---

## Must Fix

### 1. BUG: 17 duplicate IDs in live output

**`wycokck.py:113-135`** — Live crawl of `kancit_board_commissioners` produces **526 items but only 509 unique IDs**. The CivicClerk API returns the same event under multiple categories with different event IDs, but `_get_id()` generates IDs from `spider_name + datetime + title`, producing collisions.

```
ID: kancit_board_commissioners/201510011900/x/full_commission (3 duplicates)
  source: .../event/154, .../event/396, .../event/408
```

**Fix:** Deduplicate by CivicClerk event ID:
```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._seen_event_ids = set()

def parse(self, response):
    for raw_event in data.get("value", []):
        event_id = raw_event.get("id")
        if event_id is None or event_id in self._seen_event_ids:
            continue
        self._seen_event_ids.add(event_id)
```

---

### 2. BUG: `_parse_title` fails on 10 out of 11 real-world dirty titles

**`wycokck.py:158-174`** — The docstring claims "robust normalization" but testing against actual live API data shows the regex **only cleans 1 of 11 titles with embedded dates**:

| Live Title | Cleaned? | Issue |
|------------|----------|-------|
| `"8.15.24 Board of Commission Special Meeting"` | NO | Leading date (regex only handles trailing) |
| `"10.12.23 Full Commission Special Session"` | NO | Leading date |
| `"8.10.23 Full Commission Special Session"` | NO | Leading date |
| `"Special Session March 24, 2022"` | NO | Text month format |
| `"Special Session 7/24/17 6:35 PM"` | NO | Date followed by time (not at $) |
| `"Special Session 7/24/17 5:30 PM"` | NO | Date followed by time |
| `"Executive Session 12/16/21 immediately following 7 PM meeting"` | NO | Date in middle of string |
| `"Special Session 3/12/20 @ 5PM; 6 PM Special will be held"` | NO | Date in middle |
| `"Special Session 8/2/18"` | YES | Only success (trailing, no extra text) |

Additional junk titles passing through uncleaned:
- `"Distribution Testing"` — test data in production API
- `"Full Commission Test/Train Meeting"` — test meeting
- `"One Time Event"` — meaningless

**Fix:** Add leading date removal and date-followed-by-time handling:
```python
# Remove leading dates (8.15.24, 10.12.23)
title = re.sub(r"^\d{1,2}[./]\d{1,2}[./]\d{2,4}\s+", "", title)
# Remove trailing dates even when followed by time/text
title = re.sub(r"\s+\d{1,2}[./]\d{1,2}[./]\d{2,4}(\s+.*)?$", "", title)
```

---

### 3. BUG: `if not event_id` skips events with `id=0`

**`wycokck.py:114-116`** — Uses falsy check:
```python
event_id = raw_event.get("id")
if not event_id:
    continue
```

`not 0` evaluates to `True`, so any event with `id=0` would be silently skipped. Same bug at **line 220** for `file_id`:
```python
if not file_id or not event_id:
    continue
```

**Fix:** Use explicit `None` check:
```python
if event_id is None:
    continue
# ...
if file_id is None or event_id is None:
    continue
```

---

### 4. Fetching 10+ years of historical data on every crawl

**`wycokck.py:81`** — `start_date_str = "2015-05-01"` causes every crawl to fetch ALL events since 2015. Live result: **526 items** for one spider, requiring multiple paginated requests. With 7 spiders that's ~3,500+ items per run. Historical data doesn't change.

**Fix:** Use a rolling window:
```python
months_behind = 12

def start_requests(self):
    today = date.today()
    start_date = today - relativedelta(months=self.months_behind)
```

---

### 5. Classification is always COMMISSION for `kancit_board_commissioners`

**`wycokck.py:123, 142-156`** — Classification combines title + agency: `f"{title} {self.agency}"`. Since `self.agency = "Board of Commissioners - Unified Government..."` always contains "commission", the classification map **always matches "commission" first** regardless of the title.

Live proof: **All 526 items are COMMISSION** — even titles like `"Board of Zoning Appeals"`, `"Special Session"`, `"One Time Event"`, and `"Distribution Testing"`.

This means the classification logic is effectively dead code for this spider — the agency name dominates. For spiders where the agency name doesn't contain "commission" (e.g., `kancit_task_force` with agency "Committee/Task Force"), titles like "Wyandotte County Library Board" would get BOARD (from title) even though the agency category is Committee/Task Force.

**Fix:** Either:
- (a) Classify based on title only (not `f"{title} {self.agency}"`), or
- (b) Allow each spider config to set its own `classification` constant, or
- (c) At minimum, document this behavior since it produces questionable results

---

### 6. Address formatting is inconsistent

**`wycokck.py:190-212`** — The constructed address joins parts with spaces, producing inconsistent formatting compared to the default:

```
Constructed: "701 N 7th Street Commission Chambers Kansas City, KS, 66101"
Default:     "701 N 7th Street, Kansas City, KS 66101"
```

Issues:
- No comma between street and suite (`Street Commission Chambers`)
- City/state/zip uses `", "` separator producing `KS, 66101` (comma between state and zip)
- Default address has `KS 66101` (no comma — standard US format)

**Fix:** Use consistent comma-separated formatting:
```python
address_parts = filter(None, [
    event_location.get("address1"),
    event_location.get("address2"),
    event_location.get("city"),
    event_location.get("state"),
    event_location.get("zipCode"),
])
address = ", ".join(address_parts) or self.default_address
```

---

### 7. PR description doesn't match code

PR body lists **8 spiders** with names like `kancit_full_commission`, `kancit_planning_zoning`, `kancit_econ_dev_finance`. Code creates **7 spiders** with different names. Must update.

---

## Should Fix

### 8. All link URLs hardcode `/files/agenda/` path

**`wycokck.py:225`** — Every file URL uses `/files/agenda/{file_id}` regardless of type. The live API returns types "Agenda Packet", "Minutes", "Additional Documentation". Verify that `/files/agenda/` path works for non-agenda files. Since the portal is a JS app and can't be verified via HTTP, this should be manually tested.

---

### 9. No `custom_settings` for rate limiting

Both existing spiders define `custom_settings` with `ROBOTSTXT_OBEY: False` and download delays. This mixin has none. With the 2015 start date producing hundreds of paginated requests, this is especially important.

---

### 10. Test fixture is fabricated, not real API data

**`tests/files/kancit_board_commissioners.json`** — Event IDs (3001-3004), file IDs (12001, 11800), and location data are all fabricated. Real API data has:
- Different ID ranges (132, 154, 392-414, 1802, 3525-3534)
- **Null location fields for ALL events** (the fixture has full addresses)
- File types like "Agenda Packet" not "Agenda"

The fixture tests code paths that never occur in production (populated addresses) while missing real patterns. Should use actual API response data as fixtures.

---

### 11. Timezone handling unverified

**`wycokck.py:230-241`** — API returns `"2026-01-15T17:30:00Z"`. If "Z" truly means UTC, then 17:30 UTC = 11:30 AM CST — wrong for a 5:30 PM meeting. If CivicClerk returns local time with misleading "Z" (common), stripping is correct. **Must be verified** by checking meeting times against the source website.

---

## Nits

### 12. Only 1 of 7 spiders tested

Only `kancit_board_commissioners` has tests. The `kancit_task_force` spider would exercise different classification paths (category 34 has titles like "Wyandotte County Library Board", "Ethics Commission" mixed with committee-type events). At minimum, test that all 7 classes are created with correct attributes.

### 13. Module-level test setup instead of pytest fixtures

**`test_kancit_board_commissioners.py:12-25`** — Parsing runs at module import time. If import fails, all 17 tests show confusing errors. Use `@pytest.fixture` pattern.

### 14. `_parse_classification` priority is implicit

Dict order `{"commission", "board", "committee"}` is load-bearing but undocumented. "Board of Commissioners" matches "commission" not "board" due to iteration order.

### 15. No `errback` on requests

**`wycokck.py:103-104, 140`** — API errors silently produce no items.

---

## Live Crawl Results

```
Spider:     kancit_board_commissioners
Items:      526 total, 509 unique IDs (17 duplicates)
Addresses:  0 with non-default address (100% use fallback)
Classif.:   526 COMMISSION (100% — classification is effectively static)
Dirty titles remaining: 11 with embedded dates/test data
```

---

## Verdict

**Request changes.** The architecture (mixin + factory) is sound, but there are multiple bugs that affect production data quality:

| # | Issue | Severity | Type |
|---|-------|----------|------|
| 1 | Duplicate IDs (17 in live crawl) | Must fix | Bug |
| 2 | `_parse_title` fails on 10/11 dirty titles | Must fix | Bug |
| 3 | `not event_id` skips id=0 | Must fix | Bug |
| 4 | 10+ year historical fetch every crawl | Must fix | Performance |
| 5 | Classification always COMMISSION | Must fix | Logic error |
| 6 | Address formatting inconsistent | Must fix | Data quality |
| 7 | PR description mismatch | Must fix | Documentation |
| 8 | Hardcoded `/files/agenda/` path | Should fix | Unverified |
| 9 | No rate limiting settings | Should fix | Best practice |
| 10 | Fabricated test fixture | Should fix | Test quality |
| 11 | Timezone unverified | Should fix | Correctness |
