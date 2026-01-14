from .base import *  # noqa

USER_AGENT = "City Scrapers [archive mode]. Learn more and say hello at https://citybureau.org/city-scrapers"  # noqa

# Configure item pipelines
ITEM_PIPELINES = {
    "city_scrapers_core.pipelines.MeetingPipeline": 300,
}

EXTENSIONS = {
    "scrapy.extensions.closespider.CloseSpider": None,
}
