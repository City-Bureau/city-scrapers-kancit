from city_scrapers_core.constants import COMMISSION

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitPlanningZoningSpider(WycokckMixin):
    name = "kancit_planning_zoning"
    agency = "Planning & Zoning"
    category_id = 32
    classification = COMMISSION
