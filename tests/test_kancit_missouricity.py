import json
from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import (
    BOARD,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
    NOT_CLASSIFIED,
    TENTATIVE,
)
from freezegun import freeze_time

from city_scrapers.spiders.kancit_missouricity import KancitMissouricitySpider

test_response = []
with open(join(dirname(__file__), "files", "kancit_missouricity.json"), "r") as f:
    test_response = json.load(f)

spider = KancitMissouricitySpider()

freezer = freeze_time("2026-01-15")
freezer.start()

parsed_items = list(spider.parse_legistar(test_response))

freezer.stop()


def test_count():
    assert len(parsed_items) == 7


def test_title():
    assert parsed_items[0]["title"] == "City Council"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 1, 16, 9, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert parsed_items[0]["id"] == "kancit_missouricity/202601160900/x/city_council"


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


def test_classification_council():
    assert parsed_items[0]["classification"] == CITY_COUNCIL


def test_classification_committee():
    assert parsed_items[1]["classification"] == COMMITTEE


def test_classification_board():
    assert parsed_items[4]["classification"] == BOARD


def test_classification_commission():
    assert parsed_items[5]["classification"] == COMMISSION


def test_classification_not_classified():
    # Business Session doesn't match any classification keywords
    assert parsed_items[6]["classification"] == NOT_CLASSIFIED


def test_virtual_location():
    # Neighborhood Planning and Development Committee is virtual
    assert parsed_items[3]["location"]["name"] == "Virtual Meeting"
    assert parsed_items[3]["location"]["address"] == ""


def test_video_link():
    # Business Session has a video link
    links = parsed_items[6]["links"]
    video_links = [link for link in links if link["title"] == "Video"]
    assert len(video_links) == 1
    assert video_links[0]["href"] == "https://kansascity.granicus.com/player/clip/1234"


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
