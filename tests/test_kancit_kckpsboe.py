from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, COMMITTEE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.kancit_kckpsboe import KancitKckpsBoeSpider


@pytest.fixture
def spider():
    return KancitKckpsBoeSpider()


@pytest.fixture
def parsed_items(spider):
    test_response = file_response(
        join(dirname(__file__), "files", "kancit_kckpsboe.json"),
        url="https://kckps.community.highbond.com/Services/MeetingsService.svc/meetings",  # noqa
    )
    with freeze_time("2026-02-02"):
        return [item for item in spider.parse(test_response)]


def test_count(parsed_items):
    assert len(parsed_items) == 12


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "Academic Committee Meeting"


def test_description(parsed_items):
    assert parsed_items[0]["description"] == ""


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2025, 10, 28, 10, 0)


def test_end(parsed_items):
    assert parsed_items[0]["end"] is None


def test_time_notes(parsed_items):
    assert (
        parsed_items[0]["time_notes"]
        == "Please check meeting attachments for accurate time and location."
    )


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "kancit_kckps_boe/202510281000/x/academic_committee_meeting"
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == "passed"


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "Kansas Public Schools",
        "address": "2010 N. 59th Street, Kansas City, Kansas 66103",
    }


def test_source(parsed_items):
    assert (
        parsed_items[0]["source"]
        == "https://kckps.community.highbond.com/Portal/MeetingTypeList.aspx"
    )


def test_links(parsed_items):
    assert parsed_items[0]["links"] == [
        {
            "href": "https://kckps.community.highbond.com/Portal/MeetingInformation.aspx?Org=Cal&Id=574",  # noqa
            "title": "Meeting Details",
        }
    ]


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == COMMITTEE


# Test Finance Committee Meeting (index 1)
def test_finance_committee_title(parsed_items):
    assert parsed_items[1]["title"] == "Finance Committee Meeting"


def test_finance_committee_start(parsed_items):
    assert parsed_items[1]["start"] == datetime(2026, 5, 1, 13, 0)


def test_finance_committee_status(parsed_items):
    assert parsed_items[1]["status"] == "tentative"


def test_finance_committee_time_notes(parsed_items):
    assert (
        parsed_items[1]["time_notes"]
        == "Please check meeting attachments for accurate time and location. You are invited to join virtually. Please check the attachments for the virtual link."  # noqa
    )


# Test Facilities Committee Meeting (index 2)
def test_facilities_committee_title(parsed_items):
    assert parsed_items[2]["title"] == "Facilities Committee Meeting"


def test_facilities_committee_location(parsed_items):
    assert parsed_items[2]["location"] == {
        "name": "Kansas Public Schools - Third Floor East Wing",
        "address": "2010 N. 59th Street, Kansas City, Kansas 66103",
    }


# Test Board Retreat Agenda (index 3)
def test_board_retreat_title(parsed_items):
    assert parsed_items[3]["title"] == "Board Retreat Agenda"


def test_board_retreat_classification(parsed_items):
    assert parsed_items[3]["classification"] == BOARD


def test_board_retreat_location(parsed_items):
    assert parsed_items[3]["location"] == {
        "name": "McAnany Van Cleave & Phillips Law Firm",
        "address": "10 E Cambridge Circle Drive #300, Kansas City, Kansas 66103",
    }


# Test Boundary Committee Meeting (index 4)
def test_boundary_committee_start(parsed_items):
    assert parsed_items[4]["start"] == datetime(2025, 7, 17, 17, 30)


def test_boundary_committee_links(parsed_items):
    assert parsed_items[4]["links"] == [
        {
            "href": "https://kckps.community.highbond.com/Portal/MeetingInformation.aspx?Org=Cal&Id=522",  # noqa
            "title": "Meeting Details",
        }
    ]


# Test Regular Board Meeting Agenda (index 5)
def test_regular_board_meeting_title(parsed_items):
    assert parsed_items[5]["title"] == "Regular Board Meeting Agenda"


def test_regular_board_meeting_start(parsed_items):
    assert parsed_items[5]["start"] == datetime(2021, 10, 26, 17, 0)


# Test Regular Meeting Agenda (index 6)
def test_regular_meeting_title(parsed_items):
    assert parsed_items[6]["title"] == "Regular Meeting Agenda"


# Test Regular Meeting Agenda - Current (index 7)
def test_regular_meeting_current_title(parsed_items):
    assert parsed_items[7]["title"] == "Regular Meeting Agenda"


def test_regular_meeting_current_start(parsed_items):
    assert parsed_items[7]["start"] == datetime(2026, 3, 24, 9, 0)


# Test Special Board Meeting Agenda (index 8)
def test_special_board_meeting_title(parsed_items):
    assert parsed_items[8]["title"] == "Special Board Meeting Agenda"


# Test Special (Budget) Meeting Agenda (index 11)
def test_special_budget_meeting_title(parsed_items):
    assert parsed_items[11]["title"] == "Special (Budget) Meeting Agenda"


def test_special_budget_meeting_start(parsed_items):
    assert parsed_items[11]["start"] == datetime(2026, 2, 6, 13, 0)


def test_all_day(parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False
