from city_scrapers_core.constants import BOARD, COMMISSION

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitBoardCommissionersSpider(WycokckMixin):
    name = "kancit_board_commissioners"
    agency = "Board of Commissioners - Unified Government of Wyandotte County and Kansas City"  # noqa
    category_ids = [31, 33, 35, 36, 37]

    def _parse_classification(self, title):
        """
        Parse classification from meeting title.

        Categories covered:
        - 31: Full Commission
        - 33: Planning & Zoning and Board of Commission
        - 35: Board of Commissioners
        - 36: Board of Commissioners Special Meeting
        - 37: Board of Commissioners Executive Meeting
        """
        title_lower = title.lower()
        if "commission" in title_lower:
            return COMMISSION
        return BOARD
