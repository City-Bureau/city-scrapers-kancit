from city_scrapers_core.constants import COMMITTEE

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitCommitteeTaskForceSpider(WycokckMixin):
    name = "kancit_committee_task_force"
    agency = "Committee/Task Force"
    category_id = 34
    classification = COMMITTEE
