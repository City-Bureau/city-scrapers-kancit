from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, PASSED, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.colgo_wycokck_bocc import ColgoWycokckBoccSpider

# Load local JSON file for testing
test_response = file_response(
    join(dirname(__file__), "files", "colgo_wycokck_bocc.json"),
    url="https://wycokck.api.civicclerk.com/v1/Events?$filter=categoryId+in+(35,36)",
)

spider = ColgoWycokckBoccSpider()

# Freeze time for consistent test results
freezer = freeze_time("2026-01-10")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    """Test that all events are parsed."""
    assert len(parsed_items) == 3


def test_title():
    """Test that titles are correctly parsed."""
    assert parsed_items[0]["title"] == "Board of Commissioners Special Meeting"
    assert parsed_items[1]["title"] == "Board of Commissioners"
    assert parsed_items[2]["title"] == "Board of Commissioners"


def test_description():
    """Test that descriptions are correctly parsed."""
    assert (
        parsed_items[0]["description"] == "Special meeting to discuss budget amendments"
    )
    assert parsed_items[1]["description"] == ""


def test_start():
    """Test that start times are correctly parsed."""
    assert parsed_items[0]["start"] == datetime(2026, 1, 8, 17, 30)
    assert parsed_items[1]["start"] == datetime(2026, 2, 5, 17, 30)
    assert parsed_items[2]["start"] == datetime(2025, 12, 15, 17, 30)


def test_end():
    """Test that end times are correctly parsed."""
    assert parsed_items[0]["end"] == datetime(2026, 1, 8, 19, 30)
    assert parsed_items[1]["end"] is None
    assert parsed_items[2]["end"] == datetime(2025, 12, 15, 19, 0)


def test_time_notes():
    """Test that time notes are empty as expected."""
    for item in parsed_items:
        assert item["time_notes"] == ""


def test_id():
    """Test that IDs are generated correctly."""
    assert parsed_items[0]["id"] is not None
    assert "colgo_wycokck_bocc" in parsed_items[0]["id"]


def test_status():
    """Test that status is correctly determined."""
    # With freeze_time at 2026-01-10:
    # - Event on 2026-01-08 is passed
    # - Event on 2026-02-05 is tentative (future)
    # - Event on 2025-12-15 is passed
    assert parsed_items[0]["status"] == PASSED  # 2026-01-08
    assert parsed_items[1]["status"] == TENTATIVE  # 2026-02-05
    assert parsed_items[2]["status"] == PASSED  # 2025-12-15


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
        parsed_items[0]["source"] == "https://wycokck.portal.civicclerk.com/event/3570"
    )
    assert (
        parsed_items[1]["source"] == "https://wycokck.portal.civicclerk.com/event/3532"
    )


def test_links():
    """Test that links are correctly parsed."""
    # First item has one link
    assert len(parsed_items[0]["links"]) == 1
    assert parsed_items[0]["links"][0]["title"] == "Agenda"
    assert (
        parsed_items[0]["links"][0]["href"]
        == "https://wycokck.portal.civicclerk.com/event/3570/files/agenda/11976"
    )

    # Second item has no links
    assert len(parsed_items[1]["links"]) == 0

    # Third item has three links
    assert len(parsed_items[2]["links"]) == 3
    link_titles = [link["title"] for link in parsed_items[2]["links"]]
    assert "Agenda" in link_titles
    assert "Agenda Packet" in link_titles
    assert "Minutes" in link_titles


def test_classification():
    """Test that classification is BOARD for all items."""
    for item in parsed_items:
        assert item["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    """Test that all_day is False for all items."""
    assert item["all_day"] is False
