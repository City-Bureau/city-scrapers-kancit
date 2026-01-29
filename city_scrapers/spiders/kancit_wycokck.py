from city_scrapers.mixins.wycokck import CivicClerkMixin

# Common agency suffix
AGENCY_SUFFIX = " - Unified Government of Wyandotte County and Kansas City"

# Configuration for each spider
# Classification is derived from meeting title in the mixin's _parse_classification
spider_configs = [
    # Board of Commissioners (categories 31, 33, 35, 36, 37)
    {
        "class_name": "KancitBoardCommissionersSpider",
        "name": "kancit_board_commissioners",
        "agency": "Board of Commissioners" + AGENCY_SUFFIX,
        "category_ids": [31, 33, 35, 36, 37],
    },
    # Zoning and Planning (category 32)
    {
        "class_name": "KancitZoningPlanningSpider",
        "name": "kancit_zoning_planning",
        "agency": "Zoning and Planning" + AGENCY_SUFFIX,
        "category_ids": [32],
    },
    # Split committee categories into separate spiders
    # Category 27: Neighborhood & Community Development Standing Committee
    {
        "class_name": "KancitNeighborhoodDevSpider",
        "name": "kancit_neighborhood_dev",
        "agency": "Neighborhood & Community Development Standing Committee"
        + AGENCY_SUFFIX,
        "category_ids": [27],
    },
    # Category 28: Economic Development & Finance Standing Committee
    {
        "class_name": "KancitEconomicDevSpider",
        "name": "kancit_economic_dev",
        "agency": "Economic Development & Finance Standing Committee" + AGENCY_SUFFIX,
        "category_ids": [28],
    },
    # Category 29: Public Works & Safety Standing Committee
    {
        "class_name": "KancitPublicWorksSpider",
        "name": "kancit_public_works",
        "agency": "Public Works & Safety Standing Committee" + AGENCY_SUFFIX,
        "category_ids": [29],
    },
    # Category 30: Administration & Human Services Standing Committee
    {
        "class_name": "KancitAdminHumanServicesSpider",
        "name": "kancit_admin_human_services",
        "agency": "Administration & Human Services Standing Committee" + AGENCY_SUFFIX,
        "category_ids": [30],
    },
    # Category 34: Committee/Task Force
    {
        "class_name": "KancitTaskForceSpider",
        "name": "kancit_task_force",
        "agency": "Committee/Task Force" + AGENCY_SUFFIX,
        "category_ids": [34],
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
            # Build attributes dict without class_name
            attrs = {k: v for k, v in config.items() if k != "class_name"}

            # Dynamically create the spider class
            spider_class = type(
                class_name,
                (CivicClerkMixin,),
                attrs,
            )

            # Register the class in the global namespace
            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
