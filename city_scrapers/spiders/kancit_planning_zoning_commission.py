from city_scrapers_core.constants import COMMISSION

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitPlanningZoningCommissionSpider(WycokckMixin):
    name = "kancit_planning_zoning_commission"
    agency = "Planning & Zoning and Board of Commission"
    category_id = 33
    classification = COMMISSION
