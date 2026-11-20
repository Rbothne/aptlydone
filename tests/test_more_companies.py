"""Companies added in November 2026: Polinger (a RentPress list page), Keener (AppFolio), AIR Communities and
B.F. Saul (a page of building cards), JBG SMITH (its own API) and Mill Creek (the WordPress REST API)."""
import html
import json
import os
import unittest

from aptrack import discover, files, fetch
from aptrack.discover import cards, generic, jbgsmith, rentpress, wpjson
from tests.quiet import QuietTestCase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGHTMAP_PAGE = '<iframe src="https://sightmap.com/embed/map111"></iframe>'


def web(pages):
    def get(url, **options):
        if url not in pages:
            raise fetch.Gone(url)
        return pages[url].encode()
    return get


def line(name):
    return next(m for m in files.load(os.path.join(ROOT, "managers.json"), None)["managers"] if m["name"] == name)


class PolingerTests(QuietTestCase):
    PROPS = [{"property_name": "Brighton Village", "property_address": "345-A West Side Drive", "property_city": "Gaithersburg",
              "property_state": "MD", "property_zip": "20878", "property_latitude": "39.12", "property_longitude": "-77.2",
              "property_post_link": "https://www.polingerco.com/apartments/brighton-village/", "property_website": "https://brightonvillage.test/"},
             {"property_name": "Tysons Towers", "property_address": "8500 Tyspring Street", "property_city": "Vienna",
              "property_state": "VA", "property_post_link": "https://www.polingerco.com/apartments/tysons-towers/", "property_website": None},
             {"property_name": "Elsewhere", "property_state": "TX", "property_post_link": "https://www.polingerco.com/apartments/elsewhere/"}]

    def test_buildings_come_from_the_list_and_their_own_sites(self):
        page = "<div data-properties='" + html.escape(json.dumps(self.PROPS), quote=True) + "'></div>"
        own = "<div data-floorplans='[]' data-parentproperties='[]'></div>"
        get = web({"https://www.polingerco.com/apartments/": page, "https://brightonvillage.test/floorplans": own})
        found = discover.DISCOVERERS["rentpress_list"](line("Polinger"))(get)
        self.assertEqual([(b["id"], b["platform"], b["feed"]) for b in found],
                         [("polinger-brighton-village", "rentpress", "https://brightonvillage.test/floorplans"),
                          ("polinger-tysons-towers", "link", None)])
        self.assertEqual(found[0]["address"]["street"], "345-A West Side Drive")
        self.assertAlmostEqual(found[0]["lat"], 39.12)

    def test_a_list_page_without_its_data_is_come_back_to(self):
        with self.assertRaises(fetch.RateLimited):
            rentpress.listed_discoverer({"name": "Polinger", "list": "https://p.test/"})(web({"https://p.test/": "<html></html>"}))


class KeenerTests(QuietTestCase):
    def test_the_apartment_complex_is_the_place_and_listings_come_from_appfolio(self):
        office = {"@type": "RealEstateAgent", "name": "Keener", "address": {"streetAddress": "1746 N Street, NW", "addressRegion": "DC"}}
        drake = {"@type": "ApartmentComplex", "name": "The Drake", "address": {"streetAddress": "1355 17th Street, NW",
                 "addressLocality": "Washington", "addressRegion": "DC", "postalCode": "20036"},
                 "geo": {"latitude": 38.9084, "longitude": -77.0384}}
        page = "".join(f'<script type="application/ld+json">{json.dumps(n)}</script>' for n in (office, drake))
        sitemap = "<urlset><url><loc>https://keenermanagement.com/properties/the-drake/</loc></url></urlset>"
        asked = []

        def get(url, **options):
            asked.append(url)
            return web({"https://keenermanagement.com/sitemap-0.xml": sitemap,
                        "https://keenermanagement.com/properties/the-drake/": page})(url)
        (b,) = generic.discoverer(line("Keener"))(get)
        self.assertEqual((b["id"], b["name"], b["platform"], b["feed"]),
                         ("keener-the-drake", "The Drake", "appfolio", "https://keenermgmt.appfolio.com/listings#1355 17th Street, NW"))
        self.assertEqual(len(asked), 2)                       # no floor-plans pages looked for


class CardsTests(QuietTestCase):
    AIR = ('<div class="col firstCard" data-state="MD" data-city="Bethesda" data-aos="fade-up"><a href="https://www.flats.test"><img/></a>'
           '<a href="https://www.flats.test" class="commName mb-3 title"> Flats 8300 Apartment Homes </a>'
           '<p class="address description">8300 Wisconsin Avenue Bethesda, MD 20814</p></div>'
           '<div class="col firstCard" data-state="TX" data-city="Austin"><a href="https://tx.test" class="commName">Far</a>'
           '<p class="address">1 Main St Austin, TX 78701</p></div>')

    def test_air_cards_give_name_address_and_website(self):
        get = web({"https://www.aircommunities.com/en/community.html": self.AIR, "https://www.flats.test/floorplans": SIGHTMAP_PAGE})
        (b,) = cards.discoverer(line("AIR Communities"))(get)
        self.assertEqual((b["id"], b["name"], b["platform"], b["url"]),
                         ("air-communities-flats-8300-apartment-homes", "Flats 8300 Apartment Homes", "sightmap", "https://www.flats.test"))
        self.assertEqual(b["address"], {"street": "8300 Wisconsin Avenue", "city": "Bethesda", "state": "MD", "zip": "20814"})
        self.assertIsNone(b["lat"])                              # placed later by its address

    def test_split_address(self):
        self.assertEqual(cards.split_address("1325 15th St NW Washington, DC 20005", "Washington"),
                         {"street": "1325 15th St NW", "city": "Washington", "state": "DC", "zip": "20005"})
        self.assertEqual(cards.split_address("260 S Reynolds St, Alexandria, VA 22304")["city"], "Alexandria")

    def test_a_card_that_is_only_a_link_takes_its_place_from_the_buildings_site(self):
        menu = ('<ul id="menu-residential-links-only" class="menu"><li><a href="https://lyon.test/">Lyon Place</a></li>'
                '<li><a href="https://nowhere.test/">Nowhere</a></li></ul><a href="https://bank.test/">Bank</a>')
        lyon = ('<script type="application/ld+json">' + json.dumps({"@type": "ApartmentComplex", "name": "Lyon Place at Clarendon",
                "address": {"streetAddress": "1200 N Garfield Street", "addressLocality": "Arlington", "addressRegion": "VA",
                            "postalCode": "22201"}, "geo": {"latitude": 38.88, "longitude": -77.09}}) + "</script>")
        get = web({"https://bfsaul.com/properties/residential/": menu, "https://lyon.test/": lyon + SIGHTMAP_PAGE,
                   "https://nowhere.test/": "<html></html>"})
        (b,) = cards.discoverer(line("B.F. Saul"))(get)
        self.assertEqual((b["id"], b["name"], b["address"]["street"], b["lat"], b["platform"]),
                         ("b-f-saul-lyon-place", "Lyon Place", "1200 N Garfield Street", 38.88, "sightmap"))

    def test_a_page_without_cards_is_come_back_to(self):
        with self.assertRaises(fetch.RateLimited):
            cards.discoverer(line("AIR Communities"))(web({"https://www.aircommunities.com/en/community.html": "<html></html>"}))


class JbgSmithTests(QuietTestCase):
    def test_residential_properties_from_the_sitemap_and_api(self):
        sitemap = ("<urlset><url><loc>https://www.jbgsmith.com/property/office/RTC-WEST/1</loc></url>"
                   "<url><loc>https://www.jbgsmith.com/property/residential/THE-BARTLETT/3313404</loc></url></urlset>")
        record = {"status": "success", "data": {"property_website": "https://bartlett.test/", "property": {
            "name": "THE BARTLETT", "street_number": "520", "street_address": "12th Street South_O", "city": "Arlington",
            "state_code": "VA", "zip": "22202", "latitude": "38.862849", "longitude": "-77.052163"}}}
        get = web({jbgsmith.SITEMAP: sitemap, jbgsmith.API.format("3313404"): json.dumps(record),
                   "https://bartlett.test/floorplans": SIGHTMAP_PAGE})
        (b,) = jbgsmith.discover(get)
        self.assertEqual((b["id"], b["name"], b["address"]["street"], b["platform"]),
                         ("jbg-smith-the-bartlett", "The Bartlett", "520 12th Street South", "sightmap"))


class MillCreekTests(QuietTestCase):
    def test_records_from_the_rest_api_in_the_region(self):
        records = [{"id": 1267, "slug": "modera-sedici", "link": "https://millcreekplaces.com/community/modera-sedici/",
                    "title": {"rendered": "Modera Sedici"},
                    "acf": {"street_address": "2700 16th Street Northwest", "city": "Washington", "state": "District of Columbia",
                            "zip_code": "20009", "latitude": "38.925", "longitude": "-77.036",
                            "community_url": "http://www.sedici.test/?switch_cls[id]=94593/?utm_source=MillCreekPlaces"}},
                   {"id": 2, "slug": "far", "title": {"rendered": "Far"}, "acf": {"state": "Texas"}}]
        api = "https://millcreekplaces.com/wp-json/wp/v2/community"
        get = web({f"{api}?per_page=100&page=1": json.dumps(records), "http://www.sedici.test/floorplans": SIGHTMAP_PAGE})
        (b,) = wpjson.discoverer(line("Mill Creek"))(get)
        self.assertEqual((b["id"], b["name"], b["address"]["state"], b["url"], b["platform"]),
                         ("mill-creek-modera-sedici", "Modera Sedici", "DC", "http://www.sedici.test/", "sightmap"))

    def test_state_names_become_codes(self):
        self.assertEqual([wpjson.state_code(s) for s in ("District of Columbia", "Maryland", "virginia", "TX")], ["DC", "MD", "VA", "TX"])


class ManagersTests(unittest.TestCase):
    def test_paused_companies_say_why(self):
        self.assertNotIn("paused", line("JBG SMITH"))             # RentCafe sites are read now, at the owner's instruction
        self.assertIn("Cloudflare", line("Mill Creek")["paused"])
        self.assertNotIn("paused", line("Polinger"))


if __name__ == "__main__":
    unittest.main()
