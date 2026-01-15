from city_scrapers_core.constants import COMMISSION

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitFullCommissionSpider(WycokckMixin):
    name = "kancit_full_commission"
    agency = "Full Commission"
    category_id = 31
    classification = COMMISSION
