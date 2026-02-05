from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, COMMITTEE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.kancit_kckpsboe import KancitKckpsBoeSpider

test_response = file_response(
    join(dirname(__file__), "files", "kancit_kckpsboe.json"),
    url="https://kckps.community.highbond.com/Services/MeetingsService.svc/meetings",
)
spider = KancitKckpsBoeSpider()

freezer = freeze_time("2026-02-02")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) >= 12


def test_title():
    assert parsed_items[0]["title"] == "Academic Committee Meeting"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2025, 10, 28, 10, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert (
        parsed_items[0]["time_notes"]
        == "Please check meeting attachments for accurate time and location."
    )


def test_id():
    assert (
        parsed_items[0]["id"]
        == "kancit_kckps_boe/202510281000/x/academic_committee_meeting"
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Kansas City, Kansas Public Schools - Central Office and Training Center",  # noqa
        "address": "2010 N. 59th Street",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://kckps.community.highbond.com/Portal/MeetingTypeList.aspx"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "https://kckps.community.highbond.com/Portal/MeetingInformation.aspx?Org=Cal&Id=574",  # noqa
            "title": "Meeting Details",
        }
    ]


def test_classification():
    assert parsed_items[0]["classification"] == COMMITTEE


# Test Finance Committee Meeting (index 1)
def test_finance_committee_title():
    assert parsed_items[1]["title"] == "Finance Committee Meeting"


def test_finance_committee_start():
    assert parsed_items[1]["start"] == datetime(2026, 5, 1, 13, 0)


def test_finance_committee_status():
    assert parsed_items[1]["status"] == "tentative"


def test_finance_committee_time_notes():
    assert (
        parsed_items[1]["time_notes"]
        == "Please check meeting attachments for accurate time and location. You are invited to join virtually. Please check the attachments for the virtual link."  # noqa
    )


# Test Facilities Committee Meeting (index 2)
def test_facilities_committee_title():
    assert parsed_items[2]["title"] == "Facilities  Committee Meeting"


def test_facilities_committee_location():
    assert parsed_items[2]["location"] == {
        "name": "Kansas City, Kansas Public Schools - Central Office and Training Center",  # noqa
        "address": "2010 N. 59th Street, Third Floor East Wing",
    }


# Test Board Retreat Agenda (index 3)
def test_board_retreat_title():
    assert parsed_items[3]["title"] == "Board Retreat Agenda"


def test_board_retreat_classification():
    assert parsed_items[3]["classification"] == BOARD


def test_board_retreat_location():
    assert parsed_items[3]["location"] == {
        "name": "McAnany Van Cleave & Phillips Law Firm",
        "address": "10 E Cambridge Circle Drive #300, Kansas City, Kansas 66103",
    }


# Test Boundary Committee Meeting (index 4)
def test_boundary_committee_start():
    assert parsed_items[4]["start"] == datetime(2025, 7, 17, 17, 30)


def test_boundary_committee_links():
    assert parsed_items[4]["links"] == [
        {
            "href": "https://kckps.community.highbond.com/Portal/MeetingInformation.aspx?Org=Cal&Id=522",  # noqa
            "title": "Meeting Details",
        }
    ]


# Test Regular Board Meeting Agenda (index 5)
def test_regular_board_meeting_title():
    assert parsed_items[5]["title"] == "Regular Board Meeting Agenda"


def test_regular_board_meeting_start():
    assert parsed_items[5]["start"] == datetime(2021, 10, 26, 0, 0)


# Test Regular Meeting Agenda (index 6)
def test_regular_meeting_title():
    assert parsed_items[6]["title"] == "Regular Meeting Agenda"


# Test Regular Meeting Agenda - Current (index 7)
def test_regular_meeting_current_title():
    assert parsed_items[7]["title"] == "Regular Meeting Agenda - Current"


def test_regular_meeting_current_start():
    assert parsed_items[7]["start"] == datetime(2026, 3, 24, 9, 0)


# Test Special Board Meeting Agenda (index 8)
def test_special_board_meeting_title():
    assert parsed_items[8]["title"] == "Special Board Meeting Agenda"


# Test Special (Budget) Meeting Agenda (index 11)
def test_special_budget_meeting_title():
    assert parsed_items[11]["title"] == "Special (Budget) Meeting Agenda"


def test_special_budget_meeting_start():
    assert parsed_items[11]["start"] == datetime(2026, 2, 6, 13, 0)


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
