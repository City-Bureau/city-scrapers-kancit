from city_scrapers_core.constants import BOARD, COMMISSION, NOT_CLASSIFIED

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitZoningPlanningSpider(WycokckMixin):
    name = "kancit_zoning_planning"
    agency = "Zoning and Planning - Unified Government of Wyandotte County and Kansas City"  # noqa
    category_ids = [32]

    def _parse_classification(self, title):
        """
        Parse classification from meeting title.

        Categories covered:
        - 32: Planning & Zoning (includes Board of Zoning Appeals,
              Landmark Commission, City Planning Commission)
        """
        title_lower = title.lower()
        if "commission" in title_lower:
            return COMMISSION
        if "board" in title_lower:
            return BOARD
        return NOT_CLASSIFIED
