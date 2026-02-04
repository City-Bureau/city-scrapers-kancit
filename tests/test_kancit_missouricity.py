import json
from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import CITY_COUNCIL, TENTATIVE
from freezegun import freeze_time
from scrapy.http import HtmlResponse, Request

from city_scrapers.spiders import kancit_missouricity

# Get the Council spider from the factory (KancitSpider034 = Council)
KancitCouncilSpider = kancit_missouricity.KancitSpider034

# Load test data
with open(join(dirname(__file__), "files", "kancit_council.json"), "r") as f:
    test_response = json.load(f)

# Load HTML for testing _parse_legistar_events
with open(join(dirname(__file__), "files", "kancit_missouricity.html"), "r") as f:
    test_html = f.read()

spider = KancitCouncilSpider()

freezer = freeze_time("2026-01-15")
freezer.start()

parsed_items = list(spider.parse_legistar(test_response))

freezer.stop()


def test_count():
    assert len(parsed_items) == 3


def test_title():
    assert parsed_items[0]["title"] == "Council"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 1, 16, 9, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert parsed_items[0]["id"] == "kancit_council/202601160900/x/council"


def test_status():
    assert parsed_items[0]["status"] == TENTATIVE


def test_location():
    assert (
        parsed_items[0]["location"]["address"]
        == "City Hall, 26th Floor, 414 E. 12th St., Kansas City, MO 64106"
    )


def test_source():
    assert (
        parsed_items[0]["source"] == "https://clerk.kcmo.gov/MeetingDetail.aspx?ID=1001"
    )


def test_links():
    links = parsed_items[0]["links"]
    assert len(links) == 3
    assert links[0]["title"] == "Agenda"
    assert links[0]["href"] == "https://clerk.kcmo.gov/View.ashx?M=A&ID=1001"
    assert links[1]["title"] == "Minutes"
    assert links[2]["title"] == "iCalendar"


def test_classification():
    assert parsed_items[0]["classification"] == CITY_COUNCIL


def test_virtual_location():
    # Third item is virtual
    assert parsed_items[2]["location"]["name"] == "Virtual Meeting"
    assert parsed_items[2]["location"]["address"] == ""


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False


def test_parse_legistar_events_only_gets_calendar():
    """Test that _parse_legistar_events only parses gridCalendar, not upcoming."""
    html_spider = KancitCouncilSpider()
    request = Request(url="https://clerk.kcmo.gov/Calendar.aspx")
    response = HtmlResponse(
        url="https://clerk.kcmo.gov/Calendar.aspx",
        request=request,
        body=test_html.encode("utf-8"),
    )
    events = html_spider._parse_legistar_events(response)

    # HTML has 5 upcoming meetings and 58 calendar meetings
    # Should only get calendar meetings (58), not upcoming (5)
    assert len(events) == 58

    # Verify all events have valid Name fields
    for event in events:
        name = event.get("Name", {})
        if isinstance(name, dict):
            assert name.get("label") is not None
