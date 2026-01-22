from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED

from city_scrapers.mixins.wycokck import WycokckMixin

# Common agency suffix
AGENCY_SUFFIX = " - Unified Government of Wyandotte County and Kansas City"


def classify_board_commissioners(title):
    """Classification for Board of Commissioners meetings."""
    title_lower = title.lower()
    if "commission" in title_lower:
        return COMMISSION
    return BOARD


def classify_zoning_planning(title):
    """Classification for Zoning and Planning meetings."""
    title_lower = title.lower()
    if "commission" in title_lower:
        return COMMISSION
    if "board" in title_lower:
        return BOARD
    return NOT_CLASSIFIED


def classify_committee(title):
    """Classification for Committee meetings."""
    return COMMITTEE


# Configuration for each spider
spider_configs = [
    {
        "class_name": "KancitBoardCommissionersSpider",
        "name": "kancit_board_commissioners",
        "agency": "Board of Commissioners" + AGENCY_SUFFIX,
        "category_ids": [31, 33, 35, 36, 37],
        "_classification_func": classify_board_commissioners,
    },
    {
        "class_name": "KancitZoningPlanningSpider",
        "name": "kancit_zoning_planning",
        "agency": "Zoning and Planning" + AGENCY_SUFFIX,
        "category_ids": [32],
        "_classification_func": classify_zoning_planning,
    },
    {
        "class_name": "KancitCommitteeCommissionsSpider",
        "name": "kancit_committee_commissions",
        "agency": "Committee/Commissions" + AGENCY_SUFFIX,
        "category_ids": [27, 28, 29, 30, 34],
        "_classification_func": classify_committee,
    },
]


def create_spiders():
    """
    Dynamically create spider classes using the spider_configs list
    and register them in the global namespace.
    """
    for config in spider_configs:
        class_name = config["class_name"]

        if class_name not in globals():
            # Extract classification function
            classification_func = config.get("_classification_func")

            # Build attributes dict without class_name and _classification_func
            attrs = {
                k: v
                for k, v in config.items()
                if k not in ("class_name", "_classification_func")
            }

            # Add _parse_classification method if function provided
            if classification_func:
                attrs["_parse_classification"] = lambda self, title, f=classification_func: f(title)  # noqa

            # Dynamically create the spider class
            spider_class = type(
                class_name,
                (WycokckMixin,),
                attrs,
            )

            # Register the class in the global namespace
            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
