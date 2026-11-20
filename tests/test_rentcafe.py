"""RentCafe (Yardi) building websites: a floor-plans page links to one page per plan, and a plan's page lists each
available apartment with its base rent, its required monthly fees, the day it is free and what the listing says
about it. Read at the owner's instruction (2026-11-20); see README, "A building's own website"."""
import unittest

from aptrack import fetch
from aptrack.discover import common
from aptrack.readers import READERS, NotAnswering, rentcafe

BUILDING = {"id": "jbg-smith-the-example", "feed": "https://www.example-apts.com/floorplans", "url": "https://www.example-apts.com/"}
HEAD = '<script src="https://cdngeneralmvc.rentcafe.com/js/site.js"></script>'


def button(slug, name, beds, sqft, price, n, kind="apply"):
    return (f'<a href="/floorplans/{slug}" class="btn track-apply floorplan-action-button" name="applynow" '
            f'data-leasingtype="conventional" data-floorplan-name="{name}" data-floorplan-size="{beds}" '
            f'data-floorplan-sqft="{sqft}" data-floorplan-price="{price}" data-selenium-id="floorplan-{n}-{kind}-btn">Availability</a>')


LIST = HEAD + "<div id='floorplans-container'>" \
    + button("1-bed---1-bath-%7c-a05", "1 Bed - 1 Bath | A05", 1, 622, "2469 -3466", 0) \
    + button("1-bed---1-bath-%7c-a05", "1 Bed - 1 Bath | A05", 1, 622, "2469 -3466", 0) \
    + button("studio-%7c-s02", "Studio | S02", 0, 480, "1900 -2400", 1) \
    + '<a href="/floorplans/3-bed---2-bath-%7c-c01" data-floorplan-name="3 Bed - 2 Bath | C01" data-selenium-id="floorplan-2-contact-btn">Contact Us</a>' \
    + "</div>"


def apartment(code, when, base, fee, total, name, beds, sqft, term, about):
    return f'''<div class="card"><div class="card-body text-center">
      <h3 class="h5 card-title"> Apartment: <span># {code}</span> </h3>
      <p class="card-subtitle mb-2">{when}</p>
      <p> Total Monthly Leasing Price <a href="#" data-toggle="modal" data-fp-estimator-url="/rentestimate/x?unitid=9738582"
        data-fp_base_charge="{base}" data-fp_inclusive_charge="{fee}" data-fp_total_charge="{total}"
        data-floorplan-name="{name}" data-floorplan-size="{beds}" data-floorplan-sqft="{sqft}"
        data-floorplan-price="2469.00 -3201.00" data-unit-code="{code}"> <span></span> </a> </p>
      <span>Starting at:</span> $2,559
      <p> <small> Base rent $2,469 &middot; {term}-month term </small> </p>
      <div id="amenities1" class="collapse"> {about} </div></div></div>'''


TO = "&lt;span class=&#x27;sr-only&#x27;&gt;to&lt;/span&gt;"
PLAN = HEAD + '<div id="availApts" class="row my-3"><span class="sr-only">Available Units</span>' \
    + apartment("520743", "Available Now", f"$2,469 {TO} -$3,201", "$90", f"$2,559{TO}-$3,291", "1 Bed - 1 Bath | A05", "1.0", 622, 11,
                "7th Floor, Small Balcony/Patio, Espresso Finish, West") \
    + apartment("521143", "Date Available: <span> 12/26/2026</span>", f"$2,544 {TO} -$3,466", "$90", f"$2,634{TO}-$3,556",
                "1 Bed - 1 Bath | A05", "1.0", 622, 12, "11th Floor, East") \
    + "</div>"
STUDIO = HEAD + '<div id="availApts">' + apartment("S-3", "Available Now", "$1,900", "", "$1,900", "Studio | S02", "0.0", 480, 12, "") + "</div>"


def web(pages, asked=None):
    def get(url, **options):
        if asked is not None:
            asked.append(url)
        if url not in pages:
            raise fetch.Gone(url)
        return pages[url].encode()
    return get


SITE = {"https://www.example-apts.com/floorplans": LIST,
        "https://www.example-apts.com/floorplans/1-bed---1-bath-%7c-a05": PLAN,
        "https://www.example-apts.com/floorplans/studio-%7c-s02": STUDIO}


class RentCafeReaderTest(unittest.TestCase):
    def test_each_available_apartment_is_read_from_its_plans_page(self):
        asked = []
        result = READERS["rentcafe"](BUILDING, web(SITE, asked))
        units = {u["unit"]: u for u in result["units"]}
        self.assertEqual(sorted(units), ["520743", "521143", "S-3"])
        first = units["520743"]
        self.assertEqual((first["rent"], first["fees"], first["lease"]), (2469, 90, 11))       # base rent; required monthly fees apart
        self.assertEqual((first["plan"], first["beds"], first["baths"], first["sqft"], first["floor"]), ("1 Bed - 1 Bath | A05", 1, 1, 622, 7))
        self.assertIsNone(first["available"])                                                 # "Available Now"
        self.assertEqual(first["notes"], "7th Floor, Small Balcony/Patio, Espresso Finish, West")
        self.assertEqual(first["url"], "https://www.example-apts.com/floorplans/1-bed---1-bath-%7c-a05")
        second = units["521143"]
        self.assertEqual((second["rent"], second["available"], second["floor"], second["lease"]), (2544, "2026-12-26", 11, 12))
        studio = units["S-3"]
        self.assertEqual((studio["beds"], studio["rent"], studio["fees"], studio["notes"], studio["floor"]), (0, 1900, None, None, None))
        # one request for the list, one per plan that has apartments; the plan with none ("Contact Us") is not asked for
        self.assertEqual(asked, ["https://www.example-apts.com/floorplans",
                                 "https://www.example-apts.com/floorplans/1-bed---1-bath-%7c-a05",
                                 "https://www.example-apts.com/floorplans/studio-%7c-s02"])

    def test_a_plan_let_go_between_requests_is_skipped(self):
        pages = {k: v for k, v in SITE.items() if "studio" not in k}
        self.assertEqual(len(READERS["rentcafe"](BUILDING, web(pages))["units"]), 2)

    def test_a_site_with_nothing_available_reads_as_no_units(self):
        nothing = HEAD + '<div id="floorplans-container"><a data-floorplan-name="Studio | S02" data-selenium-id="floorplan-0-contact-btn">Contact Us</a></div>'
        self.assertEqual(rentcafe.read(BUILDING, web({BUILDING["feed"]: nothing}))["units"], [])

    def test_a_page_that_is_not_a_floor_plans_page_is_not_answering(self):
        for page in ("<html><title>Just a moment...</title></html>", HEAD + "<html>welcome</html>"):
            with self.assertRaises(NotAnswering):
                rentcafe.read(BUILDING, web({BUILDING["feed"]: page}))

    def test_a_blocked_plan_page_stops_the_read_rather_than_passing_as_empty(self):
        pages = dict(SITE)
        pages["https://www.example-apts.com/floorplans/studio-%7c-s02"] = "<html><title>Just a moment...</title></html>"
        with self.assertRaises(NotAnswering):
            rentcafe.read(BUILDING, web(pages))


def row(unit_id, code, sqft, when, base, fee, name, beds, term):
    """The same apartment as a row of a table, as other RentCafe sites lay a plan's page out."""
    return f'''<tr data-selenium-id="urow1" class="unit-container" id="unit-container-{unit_id}">
      <td class="td-card-name" data-selenium-id="Apt1"><p class="d-block d-lg-none td-label">Apartment:</p> #{code}</td>
      <td class="td-card-sqft"><p class="td-label">Sq. Ft.:</p> {sqft}</td>
      <td class="td-card-rent"><p> Total Monthly Leasing Price <a href="#" data-fp-estimator-url="/rentestimate/x?unitid={unit_id}"
        data-fp_base_charge="{base}" data-fp_inclusive_charge="{fee}" data-floorplan-name="{name}" data-floorplan-size="{beds}"
        data-floorplan-sqft="{sqft}" data-unit-code="{code}"></a></p> Base rent $2,033 &middot; {term}-month term</td>
      <td class="td-card-details"><p class="td-label">Amenities:</p> Dark Finish West Facing</td>
      <td class="td-card-available"><p class="td-label">Date:</p> {when}</td></tr>'''


TABLE = HEAD + "<table><tbody>"     + row(44178783, "W21114", 412, "11/26/2026", f"$2,033 {TO} -$2,831", "$65", "West Half - Studio | S02a", "0.0", 12)     + row(44178790, "W21203", 412, "Available", "$2,101", "$65", "West Half - Studio | S02a", "0.0", 12)     + "</tbody></table>"


class RentCafeTableTest(unittest.TestCase):
    def test_apartments_listed_as_table_rows_are_read_too(self):
        units = {u["unit"]: u for u in rentcafe.parse_plan(TABLE, BUILDING, "https://www.example-apts.com/floorplans/s02a")}
        self.assertEqual(sorted(units), ["W21114", "W21203"])
        first = units["W21114"]
        self.assertEqual((first["rent"], first["fees"], first["lease"], first["sqft"], first["beds"], first["available"]),
                         (2033, 65, 12, 412, 0, "2026-11-26"))
        self.assertEqual((units["W21203"]["rent"], units["W21203"]["available"]), (2101, None))       # "Date: Available"
        self.assertEqual(first["notes"], "Dark Finish West Facing")

    def test_a_plans_page_with_no_apartments_left_reads_as_none_and_a_block_page_does_not(self):
        self.assertEqual(rentcafe.parse_plan(HEAD + "<h1>Studio | S02</h1><p>Contact us</p>", BUILDING, "u"), [])
        self.assertIsNone(rentcafe.parse_plan("<html><title>Just a moment...</title></html>", BUILDING, "u"))


class RentCafeDiscoveryTest(unittest.TestCase):
    def test_a_rentcafe_floor_plans_page_is_recognised(self):
        self.assertEqual(common.recognise("https://www.example-apts.com/floorplans", LIST),
                         ("rentcafe", "https://www.example-apts.com/floorplans"))
        self.assertIsNone(common.recognise("https://www.example-apts.com/", HEAD + "<html>welcome</html>"))

    def test_the_site_search_finds_the_floor_plans_page(self):
        asked = []
        pages = {"https://www.example-apts.com/": HEAD + '<a href="/floorplans">Floor plans</a>', **SITE}
        self.assertEqual(common.site_feed(web(pages, asked), "https://www.example-apts.com/"),
                         ("rentcafe", "https://www.example-apts.com/floorplans"))
        self.assertEqual(asked, ["https://www.example-apts.com/floorplans"])

    def test_a_unit_map_on_a_rentcafe_site_is_still_preferred(self):
        embed = '<iframe src="https://sightmap.com/embed/abc123"></iframe>'
        self.assertEqual(common.recognise("https://www.example-apts.com/floorplans", LIST + embed)[0], "sightmap")


if __name__ == "__main__":
    unittest.main()
