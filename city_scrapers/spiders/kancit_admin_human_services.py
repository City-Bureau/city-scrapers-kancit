from city_scrapers_core.constants import COMMITTEE

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitAdminHumanServicesSpider(WycokckMixin):
    name = "kancit_admin_human_services"
    agency = "Administration & Human Services Standing Committee"
    category_id = 30
    classification = COMMITTEE
