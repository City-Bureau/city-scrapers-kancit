from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION, PASSED, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.kancit_full_commission import KancitFullCommissionSpider

# Load local JSON file for testing
test_response = file_response(
    join(dirname(__file__), "files", "kancit_full_commission.json"),
    url="https://wycokck.api.civicclerk.com/v1/Events?$filter=categoryId+eq+31",
)

spider = KancitFullCommissionSpider()

# Freeze time for consistent test results
freezer = freeze_time("2026-01-20")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    """Test that all events are parsed."""
    assert len(parsed_items) == 3


def test_title():
    """Test that titles are correctly parsed."""
    assert parsed_items[0]["title"] == "Full Commission"
    assert parsed_items[1]["title"] == "Full Commission"
    assert parsed_items[2]["title"] == "Full Commission"


def test_description():
    """Test that descriptions are correctly parsed."""
    assert parsed_items[0]["description"] == "Regular monthly meeting"
    assert parsed_items[1]["description"] == ""


def test_start():
    """Test that start times are correctly parsed."""
    assert parsed_items[0]["start"] == datetime(2026, 1, 15, 17, 30)
    assert parsed_items[1]["start"] == datetime(2026, 2, 19, 17, 30)
    assert parsed_items[2]["start"] == datetime(2025, 12, 18, 17, 30)


def test_end():
    """Test that end times are correctly parsed."""
    assert parsed_items[0]["end"] == datetime(2026, 1, 15, 19, 30)
    assert parsed_items[1]["end"] is None
    assert parsed_items[2]["end"] == datetime(2025, 12, 18, 19, 0)


def test_time_notes():
    """Test that time notes are empty as expected."""
    for item in parsed_items:
        assert item["time_notes"] == ""


def test_id():
    """Test that IDs are generated correctly."""
    assert parsed_items[0]["id"] is not None
    assert "kancit_full_commission" in parsed_items[0]["id"]


def test_status():
    """Test that status is correctly determined."""
    # With freeze_time at 2026-01-20:
    # - Event on 2026-01-15 is passed
    # - Event on 2026-02-19 is tentative (future)
    # - Event on 2025-12-18 is passed
    assert parsed_items[0]["status"] == PASSED  # 2026-01-15
    assert parsed_items[1]["status"] == TENTATIVE  # 2026-02-19
    assert parsed_items[2]["status"] == PASSED  # 2025-12-18


def test_location_with_address():
    """Test that location with address is correctly parsed."""
    assert parsed_items[0]["location"] == {
        "name": "Unified Government of Wyandotte County/Kansas City",
        "address": "701 N 7th Street Commission Chambers Kansas City, KS, 66101",
    }


def test_location_without_address():
    """Test that location without address uses default."""
    assert parsed_items[1]["location"] == {
        "name": "Unified Government of Wyandotte County/Kansas City",
        "address": "701 N 7th Street, Kansas City, KS 66101",
    }


def test_source():
    """Test that source URLs are correctly generated."""
    assert (
        parsed_items[0]["source"]
        == "https://wycokck.portal.civicclerk.com/event/3001"
    )
    assert (
        parsed_items[1]["source"]
        == "https://wycokck.portal.civicclerk.com/event/3002"
    )


def test_links():
    """Test that links are correctly parsed."""
    # First item has two links
    assert len(parsed_items[0]["links"]) == 2
    assert parsed_items[0]["links"][0]["title"] == "Agenda"
    assert (
        parsed_items[0]["links"][0]["href"]
        == "https://wycokck.portal.civicclerk.com/event/3001/files/agenda/12001"
    )

    # Second item has no links
    assert len(parsed_items[1]["links"]) == 0

    # Third item has two links
    assert len(parsed_items[2]["links"]) == 2
    link_titles = [link["title"] for link in parsed_items[2]["links"]]
    assert "Agenda" in link_titles
    assert "Minutes" in link_titles


def test_classification():
    """Test that classification is COMMISSION for all items."""
    for item in parsed_items:
        assert item["classification"] == COMMISSION


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    """Test that all_day is False for all items."""
    assert item["all_day"] is False
