from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import (
    BOARD,
    COMMITTEE,
    NOT_CLASSIFIED,
    PASSED,
    TENTATIVE,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy import Request

from city_scrapers.spiders.kancit_hickman_mills_pub_sc_dis import (
    KancitHickmanMillsPubScDisSpider,
)


@pytest.fixture
def test_calendar_response():
    """Load calendar AJAX HTML response (fs/elements endpoint), not the full /calendar page."""  # noqa
    return file_response(
        join(
            dirname(__file__), "files", "kancit_hickman_mills_pub_sc_dis_calendar.html"
        ),
        url="https://www.hickmanmills.org/fs/elements/9768?cal_date=2026-02-01&is_draft=false&is_load_more=true&page_id=450&parent_id=9768&_=1234567890",  # noqa
    )


@pytest.fixture
def test_api_response():
    """Load API JSON response with required metadata."""
    response = file_response(
        join(dirname(__file__), "files", "kancit_hickman_mills_pub_sc_dis.json"),
        url="https://simbli.eboardsolutions.com/Services/api/GetMeetingListing",
    )

    # Attach meta because parse_api_response uses response.meta["record_start"]...
    response.request = Request(
        url=response.url,
        meta={
            "record_start": 0,
            "connection_string": "test_connection_string",
            "security_token": "test_security_token",
        },
    )
    return response


@pytest.fixture
def spider():
    """Create spider instance within frozen time."""
    with freeze_time("2026-02-20"):
        return KancitHickmanMillsPubScDisSpider()


@pytest.fixture
def parsed_calendar_items(spider, test_calendar_response):
    """Parse calendar meetings within frozen time."""
    with freeze_time("2026-02-20"):
        items = []
        for item in spider.parse_calendar_response(test_calendar_response):
            if isinstance(item, Meeting):
                items.append(item)
        return items


@pytest.fixture
def parsed_api_items(spider, test_api_response):
    """Parse API meetings within frozen time."""
    with freeze_time("2026-02-20"):
        items = []
        for item in spider.parse_api_response(test_api_response):
            if isinstance(item, Meeting):
                items.append(item)
        return items


@pytest.fixture
def parsed_items(parsed_calendar_items, parsed_api_items):
    """Combined calendar and API items."""
    return parsed_calendar_items + parsed_api_items


def test_calendar_meeting_count(parsed_calendar_items):
    """Test that we parsed at least one calendar meeting."""
    assert len(parsed_calendar_items) >= 1


def test_calendar_meeting_structure(parsed_calendar_items):
    """Test calendar meetings have correct structure."""
    for item in parsed_calendar_items:
        assert item["title"]
        assert isinstance(item["start"], datetime)
        assert item["end"] is None
        assert item["all_day"] is False
        assert isinstance(item["location"], dict)
        assert "name" in item["location"]
        assert "address" in item["location"]
        assert isinstance(item["links"], list)
        if item["links"]:
            assert item["links"][0]["href"]
            assert item["links"][0]["title"]


def test_calendar_filters_board_related(parsed_calendar_items, spider):
    """Test that only board-related calendar events survive our filter."""
    for item in parsed_calendar_items:
        assert spider._is_board_related_calendar_event(item["title"])


def test_calendar_upcoming_marked_tentative(parsed_calendar_items):
    """Test that calendar meetings are upcoming and marked tentative (frozen at Feb 20, 2026)."""  # noqa
    for item in parsed_calendar_items:
        assert item["start"] >= datetime(2026, 2, 20)
        assert item["status"] == TENTATIVE


def test_calendar_contains_expected_meetings(parsed_calendar_items):
    """Test that calendar contains the expected meetings from the fixture."""
    assert any(
        m["title"] == "Regular Board Meeting"
        and m["start"] == datetime(2026, 3, 19, 18, 0)
        for m in parsed_calendar_items
    ), "Missing March 19, 2026 Regular Board Meeting"
    assert any(
        m["title"] == "Regular Board Meeting"
        and m["start"] == datetime(2026, 4, 16, 18, 0)
        for m in parsed_calendar_items
    ), "Missing April 16, 2026 Regular Board Meeting"


def test_api_meeting_count(parsed_api_items):
    """Test that we parsed the expected number of API meetings."""
    assert len(parsed_api_items) == 3


def test_api_first_item(parsed_api_items):
    """Test first API meeting properties."""
    if len(parsed_api_items) == 0:
        pytest.skip("No API meetings parsed")

    item = parsed_api_items[0]
    assert item["title"] == "Regular Session Board Meeting"
    assert item["start"] == datetime(2026, 2, 19, 18, 0)
    assert item["classification"] == BOARD
    assert len(item["links"]) == 1
    assert "MID=" in item["links"][0]["href"]


def test_api_meeting_structure(parsed_api_items):
    """Test API meetings have correct structure."""
    for item in parsed_api_items:
        assert item["title"]
        assert isinstance(item["start"], datetime)
        assert item["end"] is None
        assert item["all_day"] is False
        assert isinstance(item["location"], dict)
        assert "name" in item["location"]
        assert "address" in item["location"]


def test_id_and_status(parsed_items):
    """Test all meetings have valid ID and status."""
    for item in parsed_items:
        assert item["id"]
        assert item["status"] in [PASSED, TENTATIVE, "cancelled"]


def test_classification(parsed_items):
    """Test all meetings have valid classification."""
    for item in parsed_items:
        assert item["classification"] in [BOARD, COMMITTEE, NOT_CLASSIFIED]
