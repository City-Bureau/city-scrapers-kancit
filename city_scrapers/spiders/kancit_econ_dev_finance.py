from city_scrapers_core.constants import COMMITTEE

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitEconDevFinanceSpider(WycokckMixin):
    name = "kancit_econ_dev_finance"
    agency = "Economic Development & Finance Standing Committee"
    category_id = 28
    classification = COMMITTEE
