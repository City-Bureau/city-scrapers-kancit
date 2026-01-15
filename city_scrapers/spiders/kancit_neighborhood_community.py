from city_scrapers_core.constants import COMMITTEE

from city_scrapers.mixins.wycokck import WycokckMixin


class KancitNeighborhoodCommunitySpider(WycokckMixin):
    name = "kancit_neighborhood_community"
    agency = "Neighborhood & Community Development Standing Committee"
    category_id = 27
    classification = COMMITTEE
