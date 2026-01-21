from city_scrapers_core.constants import COMMITTEE

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitCommitteeCommissionsSpider(WycokckMixin):
    name = "kancit_committee_commissions"
    agency = "Committee/Commissions - Unified Government of Wyandotte County and Kansas City"  # noqa
    category_ids = [27, 28, 29, 30, 34]

    def _parse_classification(self, title):
        """
        Parse classification from meeting title.

        Categories covered:
        - 27: Neighborhood & Community Development Standing Committee
        - 28: Economic Development & Finance Standing Committee
        - 29: Public Works & Safety Standing Committee
        - 30: Administration & Human Services Standing Committee
        - 34: Committee/Task Force
        """
        return COMMITTEE
