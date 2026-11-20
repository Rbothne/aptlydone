"""Buildings' own websites: recognising the listing system a site uses, and reading the systems added for them
(Jonah Digital, G5's inventory service, schema.org offers on plan pages, AppFolio listing pages)."""
import copy
import json
import unittest

from aptrack import discovery, fetch
from aptrack.discover import common
from aptrack.readers import READERS, NotAnswering, ReadError, appfolio, g5, jonah, offers, sightmap
from tests.quiet import QuietTestCase


def web(pages, asked=None):
    """A fake `get`: pages maps address -> text (or a function of the POSTed body); anything else is gone."""
    def get(url, **options):
        if asked is not None:
            asked.append(url)
        if url not in pages:
            raise fetch.Gone(url)
        page = pages[url]
        if callable(page):
            page = page(json.loads(options["data"]))
        return page.encode() if isinstance(page, str) else page
    return get


def script(kind, data, attributes=""):
    return f'<script type="application/{kind}"{attributes}>{json.dumps(data)}</script>'


# --- Jonah Digital ---------------------------------------------------------------------------------------------

JONAH_DATA = {
    "floorplans": [{"id": 303, "title": "B1"}],
    "units": [
        {"type": "unit", "id": 1, "apartment_number": "320", "floorplan_id": 303, "floorplan_title": "B1", "building": "1",
         "bedrooms": "2", "bathrooms": "2", "square_feet": "948", "rent_min": "3485.06",
         "permalink": "/communities/x/floorplans/unit-abc/",
         "price_entity": {"date": "2026-08-27", "pricingReflectFees": True,
                          "adjusted": {"low_no_fees": "3431", "low": "3485.06"}}, "specials": []},
        {"type": "unit", "id": 2, "apartment_number": "411", "floorplan_id": 303, "building": "1",
         "bedrooms": "1", "bathrooms": "1", "square_feet": "700", "rent_min": "2697", "price_entity": {}},
    ],
}
JONAH_PAGE = "<html>" + script("json", JONAH_DATA, ' id="jd-fp-data-script-app"') + "</html>"
JONAH_B = {"id": "x-overture", "feed": "https://liveoverture.com/communities/x/floorplans/", "url": "https://liveoverture.com/"}


class JonahTests(unittest.TestCase):
    def test_units_have_base_rent_and_required_fees_apart(self):
        got = {u["unit"]: u for u in jonah.parse(JONAH_PAGE, JONAH_B)["units"]}
        u = got["320"]
        self.assertEqual((u["rent"], u["fees"], u["plan"], u["beds"], u["baths"], u["sqft"], u["available"]),
                         (3431, 54.06, "B1", 2, 2, 948, "2026-08-27"))
        self.assertEqual(u["url"], "https://liveoverture.com/communities/x/floorplans/unit-abc/")

    def test_a_unit_without_a_price_breakdown_takes_its_listed_rent(self):
        u = {u["unit"]: u for u in jonah.parse(JONAH_PAGE, JONAH_B)["units"]}["411"]
        self.assertEqual((u["rent"], u["fees"], u["plan"]), (2697, None, "B1"))

    def test_the_same_number_in_two_buildings_is_kept_apart(self):
        data = copy.deepcopy(JONAH_DATA)
        data["units"][1].update(apartment_number="320", building="2")
        page = script("json", data, ' id="jd-fp-data-script-app"')
        self.assertEqual(sorted(u["unit"] for u in jonah.parse(page, JONAH_B)["units"]), ["1-320", "2-320"])

    def test_a_page_without_its_data_is_not_answering(self):
        with self.assertRaises(NotAnswering):
            jonah.parse("<html>Checking your browser</html>", JONAH_B)


# --- G5 inventory --------------------------------------------------------------------------------------------

G5_PAGE = '<html>' + script("json", {"locationUrn": "g5-cl-abc", "inventoryHost": "https://inventory.test", "sightmapID": ""},
                            ' id="floor-plans-plus-config"') + '</html>'
G5_B = {"id": "greystar-chase", "feed": "https://www.chase.test/apartments/va/sterling/floor-plans"}


def g5_service(show_units=True):
    def answer(body):
        if "apartmentComplex" in body["query"]:
            assert body["variables"]["locationUrn"] == "g5-cl-abc"
            return json.dumps({"data": {"apartmentComplex": {"showUnits": show_units, "floorplans": [
                {"id": "10", "name": "1x1B", "totalAvailableUnits": 2, "beds": 1, "baths": "1.0", "sqft": 875, "startingRate": 1956},
                {"id": "11", "name": "3x2A", "totalAvailableUnits": 0, "beds": 3, "baths": "2.0", "sqft": 1556, "startingRate": 0}]}}})
        assert body["variables"]["floorplanId"] == "10"
        return json.dumps({"data": {"units": [
            {"name": "304", "displayName": "1229-304", "sqftDisplay": "875", "availabilityDate": "2026-11-08", "specials": [],
             "prices": [{"priceType": "rate", "value": "2043.0", "leaseTermBasisMin": "9"},
                        {"priceType": "total_rent", "value": "2083.0", "leaseTermBasisMin": "9"}]},
            {"name": "102", "displayName": "1226-102", "sqftDisplay": "875", "availabilityDate": "2026-12-16", "specials": [{"name": "1 month free"}],
             "prices": [{"priceType": "rate", "value": "1956.0", "leaseTermBasisMin": "12"}]}]}})
    return answer


class G5Tests(unittest.TestCase):
    def test_units_come_from_the_inventory_service_for_plans_with_any_available(self):
        asked = []
        get = web({G5_B["feed"]: G5_PAGE, "https://inventory.test/graphql": g5_service()}, asked)
        got = {u["unit"]: u for u in g5.read(G5_B, get)["units"]}
        self.assertEqual(set(got), {"1229-304", "1226-102"})
        u = got["1229-304"]
        self.assertEqual((u["rent"], u["fees"], u["lease"], u["plan"], u["beds"], u["sqft"], u["available"]),
                         (2043, 40, 9, "1x1B", 1, 875, "2026-11-08"))
        self.assertEqual(got["1226-102"]["special"], "1 month free")
        self.assertEqual(asked.count("https://inventory.test/graphql"), 2)       # the plan with none available is not asked about

    def test_a_site_that_hides_its_units_gives_one_entry_per_plan(self):
        get = web({G5_B["feed"]: G5_PAGE, "https://inventory.test/graphql": g5_service(show_units=False)})
        (u,) = g5.read(G5_B, get)["units"]
        self.assertEqual((u["unit"], u["rent"], u["count"]), ("1x1B", 1956, 2))

    def test_a_refused_question_is_not_answering(self):
        get = web({G5_B["feed"]: G5_PAGE, "https://inventory.test/graphql": lambda body: json.dumps({"errors": [{"message": "no"}]})})
        with self.assertRaises(NotAnswering):
            g5.read(G5_B, get)

    def test_a_page_without_the_widget_is_not_answering(self):
        with self.assertRaises(NotAnswering):
            g5.read(G5_B, web({G5_B["feed"]: "<html></html>"}))


# --- schema.org offers on floor-plan pages ---------------------------------------------------------------------

def plan_page(name, offers_, beds="3"):
    nodes = [{"@type": "FloorPlan", "name": name, "numberOfBedrooms": beds, "numberOfBathroomsTotal": "2",
              "floorSize": {"minValue": "1699"}, "layoutImage": "https://cdn.test/c1.jpg"}]
    nodes += [{"@type": "OfferForLease", "name": f"Unit {number}", "availability": "https://schema.org/InStock",
               "priceSpecification": {"price": price}} for number, price in offers_]
    return "".join(script("ld+json", n) for n in nodes)


AVAILABILITY = ('<a href="/availability/aerie/3-bedroom/c1" class="x">C1</a>'
                '<a href="/availability/zephyr/studio/s1">S1</a><a href="/availability/aerie/3-bedroom/c1">again</a>')
OFFERS_B = {"id": "greystar-aerie", "url": "https://www.wardman.test/aerie-apartments/",
            "feed": "https://www.wardman.test/aerie-apartments/availability"}


class OffersTests(unittest.TestCase):
    def test_plan_pages_of_this_building_only(self):
        self.assertEqual(offers.plan_links(AVAILABILITY, OFFERS_B["feed"], OFFERS_B["url"]),
                         ["https://www.wardman.test/availability/aerie/3-bedroom/c1"])
        self.assertEqual(len(offers.plan_links(AVAILABILITY, OFFERS_B["feed"])), 2)          # whose building is not known

    def test_each_offer_is_a_unit_with_its_plans_details(self):
        get = web({OFFERS_B["feed"]: AVAILABILITY,
                   "https://www.wardman.test/availability/aerie/3-bedroom/c1": plan_page("C1", [("0321", "8732.0"), ("0421", "8757.0")])})
        got = {u["unit"]: u for u in offers.read(OFFERS_B, get)["units"]}
        self.assertEqual(set(got), {"0321", "0421"})
        u = got["0321"]
        self.assertEqual((u["rent"], u["plan"], u["beds"], u["baths"], u["sqft"], u["plan_image"]),
                         (8732, "C1", 3, 2, 1699, "https://cdn.test/c1.jpg"))

    def test_air_communities_list_units_with_a_starting_price_in_words(self):
        plan = script("ld+json", {"@type": "FloorPlan", "name": "Design 1A10", "numberOfBedrooms": "1.0", "numberOfBathroomsTotal": "1.0",
                                  "floorSize": {"value": "671.0"}})
        plan += script("ld+json", {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "item": {"@type": "Apartment", "name": "247",
                                           "floorSize": {"description": "Unit #247, Starting at $2473.0", "value": "721.0"}}}]})
        home = '<a href="/floor-plan/1-bedroom/design-1a10.html">1A10</a><a href="/floor-plan/1-bedroom/design-1a10/247.html">unit</a>'
        b = {"id": "air-flats", "url": "https://www.flats.test", "feed": "https://www.flats.test"}
        self.assertEqual(common.recognise(b["feed"], home), ("offers", b["feed"]))
        (u,) = offers.read(b, web({b["feed"]: home, "https://www.flats.test/floor-plan/1-bedroom/design-1a10.html": plan}))["units"]
        self.assertEqual((u["unit"], u["rent"], u["sqft"], u["beds"], u["plan"]), ("247", 2473, 721, 1, "Design 1A10"))
        self.assertIn("required monthly fees", u["notes"])

    def test_a_page_without_plans_is_not_answering(self):
        with self.assertRaises(NotAnswering):
            offers.read(OFFERS_B, web({OFFERS_B["feed"]: "<html></html>"}))


# --- AppFolio ------------------------------------------------------------------------------------------------

def listing(number, street, rent, beds="1 bd / 1 ba", sqft="600", available="NOW", title="Nice place"):
    return (f'<div class="listing-item result js-listing-item" id="listing_{number}">'
            f'<dl><dt class="detail-box__label">RENT</dt><dd class="detail-box__value">{rent}</dd>'
            f'<dt class="detail-box__label">Square Feet</dt><dd class="detail-box__value">{sqft}</dd>'
            f'<dt class="detail-box__label">Bed / Bath</dt><dd class="detail-box__value">{beds}</dd>'
            f'<dt class="detail-box__label">Available</dt><dd class="detail-box__value js-listing-available">{available}</dd></dl>'
            f'<h2 class="listing-item__title js-listing-title"><a href="/listings/detail/{number}" target="_blank">{title}</a></h2>'
            f'<span class="u-pad-rm js-listing-address">{street}, Washington, DC 20010</span></div>')


LISTINGS = ('<html><div class="listings">' + listing(1, "3300 16th Street, NW, #905", "$1,525", "Studio / 1 ba", "405")
            + listing(2, "3300 16th Street NW Unit 811", "$1,595", available="12/15/26", title="APPLY BY 11/30 AND GET $50 OFF")
            + listing(3, "1355 17th Street, NW, #204", "$2,350") + '</div><footer></footer></html>')


class AppFolioTests(unittest.TestCase):
    def setUp(self):
        appfolio._cache.clear()

    def test_a_buildings_listings_are_those_at_its_street_address(self):
        b = {"id": "keener-the-park-monroe", "feed": "https://keener.appfolio.test/listings#3300 16th Street, NW"}
        got = {u["unit"]: u for u in appfolio.read(b, web({"https://keener.appfolio.test/listings": LISTINGS}))["units"]}
        self.assertEqual(set(got), {"905", "811"})
        self.assertEqual((got["905"]["rent"], got["905"]["beds"], got["905"]["baths"], got["905"]["sqft"], got["905"]["available"]),
                         (1525, 0, 1, 405, None))
        self.assertEqual((got["811"]["available"], got["811"]["beds"]), ("2026-12-15", 1))
        self.assertIn("$50 OFF", got["811"]["special"])
        self.assertIsNone(got["905"]["special"])
        self.assertEqual(got["905"]["url"], "https://keener.appfolio.test/listings/detail/1")

    def test_the_page_is_asked_for_once_for_all_of_a_companys_buildings(self):
        asked = []
        get = web({"https://keener.appfolio.test/listings": LISTINGS}, asked)
        for street in ("3300 16th Street, NW", "1355 17th Street, NW", "2070 Belmont Road, NW"):
            appfolio.read({"id": "k", "feed": f"https://keener.appfolio.test/listings#{street}"}, get)
        self.assertEqual(len(asked), 1)

    def test_a_building_with_nothing_listed_has_no_units(self):
        b = {"id": "k", "feed": "https://keener.appfolio.test/listings#2070 Belmont Road, NW"}
        self.assertEqual(appfolio.read(b, web({"https://keener.appfolio.test/listings": LISTINGS}))["units"], [])


# --- recognising a building website's listing system -------------------------------------------------------------

class RecogniseTests(QuietTestCase):
    def test_each_listing_system_by_what_its_page_carries(self):
        url = "https://site.test/floorplans"
        self.assertEqual(common.recognise(url, '<iframe src="https://sightmap.com/embed/abc123">'), ("sightmap", "https://sightmap.com/embed/abc123"))
        self.assertEqual(common.recognise(url, JONAH_PAGE), ("jonah", url))
        self.assertEqual(common.recognise(url, G5_PAGE), ("g5", url))
        with_map = G5_PAGE.replace('"sightmapID": ""', '"sightmapID": "xyz789"')
        self.assertEqual(common.recognise(url, with_map), ("sightmap", "https://sightmap.com/embed/xyz789"))
        self.assertEqual(common.recognise(url, AVAILABILITY), ("offers", url))
        self.assertIsNone(common.recognise(url, "<html>ysi.unitsList = [];</html>"))      # RentCafe: its terms forbid reading it
        self.assertIsNone(common.recognise(url, "<html></html>"))

    def test_listing_links_are_the_sites_own_floor_plan_and_availability_pages(self):
        page = ('<a href="/floor-plans/">Plans</a><a href="https://other.test/floorplans">x</a><a href="/gallery">g</a>'
                '<a href="/floor-plans/${tiktokUrl}">junk</a><a href="/availability/a/b/c">one plan</a><a href="/brochure-floorplans.pdf">pdf</a>')
        self.assertEqual(common.listing_links(page, "https://site.test/"), ["https://site.test/floor-plans/"])

    def test_site_feed_follows_the_sites_own_links_to_its_listings(self):
        asked = []
        get = web({"https://site.test/": '<a href="/apartments/va/sterling/floor-plans">Floor plans</a>',
                   "https://site.test/apartments/va/sterling/floor-plans": G5_PAGE}, asked)
        self.assertEqual(common.site_feed(get, "https://site.test/"), ("g5", "https://site.test/apartments/va/sterling/floor-plans"))
        self.assertEqual(asked, ["https://site.test/floorplans", "https://site.test/floor-plans", "https://site.test/",
                                 "https://site.test/apartments/va/sterling/floor-plans"])

    def test_site_feed_tries_the_availability_page_and_gives_up_as_a_link(self):
        asked = []
        get = web({"https://site.test/": "<html>Welcome</html>", "https://site.test/availability": AVAILABILITY}, asked)
        self.assertEqual(common.site_feed(get, "https://site.test/"), ("offers", "https://site.test/availability"))
        self.assertEqual(common.site_feed(web({"https://site.test/": "<html></html>"}), "https://site.test/"), ("link", None))

    def test_a_rentcafe_site_is_not_looked_through(self):
        asked = []
        page = '<script>ysi.SiteId = 123;</script><a href="/floorplans/a1">A1</a>'
        self.assertEqual(common.site_feed(web({"https://site.test/floorplans": page}, asked), "https://site.test/"), ("link", None))
        self.assertEqual(asked, ["https://site.test/floorplans"])

    def test_site_feed_asks_a_limited_number_of_pages(self):
        many = "".join(f'<a href="/floorplans/p{n}">p</a>' for n in range(30))
        asked = []
        common.site_feed(web({"https://site.test/": many}, asked), "https://site.test/")
        self.assertLessEqual(len(asked), common.SITE_PAGES)

    def test_a_site_that_says_slow_down_stops_the_search(self):
        def get(url, **options):
            raise fetch.RateLimited(url)
        with self.assertRaises(fetch.RateLimited):
            common.site_feed(get, "https://site.test/")

    def test_ids_are_made_of_letters_digits_and_dashes(self):
        b = common.building("B.F. Saul", "lyon-place", "https://lyonplace.test/", {"name": "Lyon Place", "address": {}, "lat": None, "lon": None}, None)
        self.assertEqual(b["id"], "b-f-saul-lyon-place")


class MergeTests(unittest.TestCase):
    def test_a_website_that_refused_this_week_keeps_the_listing_found_before(self):
        old = {"id": "g-a", "manager": "G", "url": "https://a.test/", "platform": "g5", "feed": "https://a.test/fp"}
        new = dict(old, platform="link", feed=None)
        (merged,) = discovery.merge([old], {"G": [new]}, "2026-11-20")
        self.assertEqual((merged["platform"], merged["feed"]), ("g5", "https://a.test/fp"))

    def test_a_website_that_changed_system_takes_the_new_one(self):
        old = {"id": "g-a", "manager": "G", "url": "https://a.test/", "platform": "g5", "feed": "https://a.test/fp"}
        new = dict(old, platform="sightmap", feed="https://sightmap.com/embed/x")
        (merged,) = discovery.merge([old], {"G": [new]}, "2026-11-20")
        self.assertEqual(merged["platform"], "sightmap")


class SightMapWithoutListingsTests(unittest.TestCase):
    def test_a_map_of_every_apartment_with_no_listing_says_so(self):
        feed = {"data": {"units": [{"unit_number": "101", "price": None, "available_on": None, "status": None}]}}
        with self.assertRaisesRegex(ReadError, "publishes no availability"):
            sightmap.parse(feed, {"id": "bozzuto-x"})


class RegisteredTests(unittest.TestCase):
    def test_new_readers_are_registered_and_rentcafe_is_not(self):
        for name, module in (("jonah", jonah), ("g5", g5), ("offers", offers), ("appfolio", appfolio)):
            self.assertIs(READERS[name], module.read)
        self.assertNotIn("rentcafe", READERS)


class PostTests(unittest.TestCase):
    def test_data_makes_a_post(self):
        seen = {}

        class Answer:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b"{}"

        def opener(request, timeout):
            seen.update(method=request.get_method(), data=request.data)
            return Answer()
        fetch.get("https://x.test/graphql", data=b'{"q": 1}', opener=opener)
        self.assertEqual(seen, {"method": "POST", "data": b'{"q": 1}'})
        fetch.get("https://x.test/", opener=opener)
        self.assertEqual(seen["method"], "GET")


if __name__ == "__main__":
    unittest.main()
