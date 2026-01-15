from city_scrapers_core.constants import COMMITTEE

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitPublicWorksSafetySpider(WycokckMixin):
    name = "kancit_public_works_safety"
    agency = "Public Works & Safety Standing Committee"
    category_id = 29
    classification = COMMITTEE
