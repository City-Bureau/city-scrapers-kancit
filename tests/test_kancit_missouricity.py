import json
from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import CITY_COUNCIL, PASSED
from freezegun import freeze_time

from city_scrapers.spiders import kancit_missouricity

KancitCouncilSpider = kancit_missouricity.KancitSpider034

with open(join(dirname(__file__), "files", "kancit_council.json"), "r") as f:
    test_response = json.load(f)

spider = KancitCouncilSpider()

freezer = freeze_time("2026-03-01")
freezer.start()

parsed_items = list(spider.parse_legistar(test_response))

freezer.stop()


def test_count():
    assert len(parsed_items) == 3


def test_title():
    assert parsed_items[0]["title"] == "Council"


def test_description():
    assert parsed_items[0]["description"] == (
        "Council meetings are also held virtually. Please check the meeting attachment for details on how to attend."  # noqa
    )


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 1, 16, 9, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert parsed_items[0]["id"] == "kancit_034/202601160900/x/council"


def test_status():
    assert parsed_items[0]["status"] == PASSED


def test_location():
    assert (
        parsed_items[0]["location"]["address"] == "414 E 12th St, Kansas City, MO 64106"
    )


def test_source():
    assert (
        parsed_items[0]["source"] == "https://clerk.kcmo.gov/MeetingDetail.aspx?ID=1001"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "https://clerk.kcmo.gov/View.ashx?M=A&ID=1001",
            "title": "Agenda",
        },
        {
            "href": "https://clerk.kcmo.gov/View.ashx?M=M&ID=1001",
            "title": "Minutes",
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == CITY_COUNCIL


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
