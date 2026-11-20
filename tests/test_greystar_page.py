"""Greystar's own page for a building carries, in the data it hands its scripts, every apartment that is free:
its number, size, floor, the day it is free, its lowest rent and the lease length that rent is for, with the
building's floor plans and its required monthly fees. It is the route for Greystar buildings whose own websites
cannot be read apartment by apartment (many refuse the tracker); the company page answers ordinary requests."""
import json
import unittest

from aptrack import fetch
from aptrack.discover import greystar as finder
from aptrack.readers import READERS, NotAnswering, greystar as reader

URL = "https://www.greystar.com/avana-bellemeade-leesburg-va/p_21810"
PLACE = ('<script type="application/ld+json">' + json.dumps({
    "@context": "https://schema.org", "@type": "LodgingBusiness", "name": "Avana Bellemeade",
    "address": {"@type": "PostalAddress", "streetAddress": "703 Clark Ct NE", "addressLocality": "Leesburg", "addressRegion": "VA", "postalCode": "20176"},
    "latitude": 39.11, "longitude": -77.55}) + "</script>")


def unit(number, plan, floor, area, low, term, when):
    return {"area": area, "availableOn": when, "floorPlanId": plan, "floorPlanLabel": "The " + plan, "floorLabel": f"Floor {floor}",
            "floorShortLabel": str(floor), "buildingLabel": "2", "maxPrice": low + 3000, "minPrice": low, "minBaseRentLeaseTerm": str(term),
            "rentMatrixStart": "2026-11-19", "rentMatrix": {"00-03": low + 500, "00-15": low}, "unitId": "79" + number, "unitNumber": number}


def page(units, fees=36.06, site="https://www.avanabellemeade.com/"):
    """A company page as the site builds it: its data arrives in pieces, each a string pushed to the page's scripts."""
    data = {"property": {"communityWebsiteUrl": site,
                         "floorplans": [{"id": "A", "bathroomCount": 1, "bedroomCount": 1, "label": "The A", "imageUrl": "https://img.test/a.png"},
                                        {"id": "S", "bathroomCount": 1, "bedroomCount": 0, "label": "The S", "imageUrl": ""}],
                         "monthlyFees": {"requiredMonthlyFeesMin": fees, "requiredMonthlyFeesMax": fees}}}
    text = "1f:" + json.dumps(data)[:-1] + (',"propertyUnits":' + json.dumps(units) if units is not None else "") + "}"
    half = len(text) // 2
    pieces = "".join(f"<script>self.__next_f.push([1,{json.dumps(part)}])</script>" for part in (text[:half], text[half:]))
    return "<html>" + PLACE + pieces + "</html>"


UNITS = [unit("0206", "A", 2, 904, 2514, 15, "2026-07-22"), unit("1016", "S", 1, 677, 1911, 12, "2026-12-09")]
BUILDING = {"id": "greystar-avana-bellemeade-leesburg-va", "feed": URL, "url": "https://www.avanabellemeade.com/"}


def web(pages, asked=None):
    def get(url, **options):
        if asked is not None:
            asked.append(url)
        if url not in pages:
            raise fetch.Gone(url)
        return pages[url].encode()
    return get


class GreystarPageReaderTest(unittest.TestCase):
    def test_each_apartment_in_the_pages_data_is_read(self):
        result = READERS["greystar"](BUILDING, web({URL: page(UNITS)}))
        units = {u["unit"]: u for u in result["units"]}
        self.assertEqual(sorted(units), ["0206", "1016"])
        first = units["0206"]
        self.assertEqual((first["rent"], first["lease"], first["sqft"], first["floor"], first["available"]), (2514, 15, 904, 2, "2026-07-22"))
        self.assertEqual((first["plan"], first["beds"], first["baths"], first["fees"], first["plan_image"]), ("The A", 1, 1, 36.06, "https://img.test/a.png"))
        self.assertEqual(first["url"], URL)
        self.assertEqual((units["1016"]["beds"], units["1016"]["rent"], units["1016"]["lease"]), (0, 1911, 12))

    def test_a_building_with_nothing_free_reads_as_no_units(self):
        self.assertEqual(reader.read(BUILDING, web({URL: page([])}))["units"], [])

    def test_a_page_without_that_data_is_not_answering(self):
        for html in (page(None), "<html><title>Just a moment...</title></html>"):
            with self.assertRaises(NotAnswering):
                reader.read(BUILDING, web({URL: html}))

    def test_no_fees_stated_means_none_recorded(self):
        (only,) = reader.read(BUILDING, web({URL: page(UNITS[:1], fees=None)}))["units"]
        self.assertIsNone(only["fees"])


class GreystarPageDiscoveryTest(unittest.TestCase):
    def test_a_building_whose_own_site_cannot_be_read_by_apartment_is_read_from_the_company_page(self):
        building = finder.parse(URL, page(UNITS), ("link", None))
        self.assertEqual((building["platform"], building["feed"]), ("greystar", URL))
        self.assertEqual(building["url"], "https://www.avanabellemeade.com/")
        refused = finder.parse(URL, page(UNITS), ("rentcafe", "https://www.avanabellemeade.com/floorplans"))
        self.assertEqual(refused["platform"], "greystar")

    def test_a_unit_map_on_the_buildings_own_site_is_still_used(self):
        building = finder.parse(URL, page(UNITS), ("sightmap", "https://sightmap.com/embed/abc123"))
        self.assertEqual((building["platform"], building["feed"]), ("sightmap", "https://sightmap.com/embed/abc123"))

    def test_a_company_page_without_apartments_in_its_data_stays_as_it_was(self):
        building = finder.parse(URL, page(None), ("link", None))
        self.assertEqual(building["platform"], "link")


if __name__ == "__main__":
    unittest.main()
