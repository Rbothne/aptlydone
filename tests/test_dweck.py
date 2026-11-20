"""Dweck Properties: its own site has a page per community that lists every available apartment there as a card,
and carries the community's name, address and coordinates. Its robots file asks for five minutes between requests,
so a community is one request and the communities are read a few per run (see aptrack/spread.py)."""
import unittest

from aptrack import fetch
from aptrack.discover import DISCOVERERS, dweck as finder
from aptrack.readers import READERS, NotAnswering, dweck as reader

SITEMAP = ("<urlset><url><loc>https://www.dweckproperties.com/communities/crystal-city-lofts/</loc></url>"
           "<url><loc>https://www.dweckproperties.com/communities/far-away/</loc></url>"
           "<url><loc>https://www.dweckproperties.com/communities/</loc></url></urlset>")


def details(name, address, where="38.863824, -77.049522"):
    return (f'<span id="property-details" data-property-link="https://www.example.com?x=1" data-property-name="{name}" '
            f'data-address="{address}" data-property-img="x.jpg" data-property-lat-long="{where}"></span>')


def row(slug, label, soon, plan, sqft, price, when):
    hidden = "" if soon else " hiddens"
    return f'''<div class="listing lists_2 list_2 Bedroom"> <a href="https://www.dweckproperties.com/availabilities/{slug}" class="bacjing"></a>
      <div class="list_title">#{label}</div> <h3>{plan}</h3> <div class="sqft">{sqft} SQ FT</div>
      <div class="fp_viewer"> <div class="overlayer_fp_img hiddens imgholdrs"> <div class="cssoo{hidden}"><span>Coming Soon</span></div> </div> </div>
      <div class="list_prices"> <div class="specials">$</div> Starting at {price}/month </div>
      <div class="list_avai">{when}</div> </div>'''


# The page also shows a few apartments again as picture cards; those repeat rows and are not read twice.
FEATURED = '''<a href="https://www.dweckproperties.com/availabilities/2203-1236434" class="avail_item"> <div class="item">
  <h4>Studio /1 Baths <span class="sq_ft">541 SQ FT</span></h4> <div class="prices"> Starting at $2,162/month </div> </div> </a>'''
LOFTS = details("Crystal City Lofts", "305 10th St S, Arlington, VA 22202") + FEATURED \
    + row("2203-1236434", "2203", False, "Studio 1 Bath", 541, "$2,162", "AVAILABLE NOW") \
    + row("56w-1713-1236434/", "56w-1713", True, "1 Bed/ 2 Bath", 966, "$3,423", "AVAILABLE 01/09/2027") \
    + row("1812-431-", "1812-431", False, "2 Bed/ 2 Bath", "1,104", "$4,010", "AVAILABLE 12/24/2026")
FAR = details("Far Away", "1 Main St, Austin, TX 78701", "30.2, -97.7")
BUILDING = {"id": "dweck-crystal-city-lofts", "feed": "https://www.dweckproperties.com/communities/crystal-city-lofts/"}


def web(pages, asked=None):
    def get(url, **options):
        if asked is not None:
            asked.append(url)
        if url not in pages:
            raise fetch.Gone(url)
        return pages[url].encode()
    return get


class DweckReaderTest(unittest.TestCase):
    def test_every_row_is_an_apartment_with_its_starting_price_and_its_date(self):
        asked = []
        result = READERS["dweck"](BUILDING, web({BUILDING["feed"]: LOFTS}, asked))
        units = {u["unit"]: u for u in result["units"]}
        self.assertEqual(sorted(units), ["1812-431", "2203", "56w-1713"])
        studio = units["2203"]
        self.assertEqual((studio["beds"], studio["baths"], studio["sqft"], studio["rent"], studio["plan"]), (0, 1, 541, 2162, "Studio 1 Bath"))
        self.assertEqual(studio["url"], "https://www.dweckproperties.com/availabilities/2203-1236434")
        self.assertEqual((studio["notes"], studio["available"]), ("the site's starting price", None))          # "AVAILABLE NOW"
        later = units["56w-1713"]
        self.assertEqual((later["beds"], later["baths"], later["rent"], later["available"]), (1, 2, 3423, "2027-01-09"))
        self.assertIn("coming soon", later["notes"])
        self.assertEqual((units["1812-431"]["beds"], units["1812-431"]["sqft"], units["1812-431"]["rent"], units["1812-431"]["available"]),
                         (2, 1104, 4010, "2026-12-24"))
        self.assertEqual(asked, [BUILDING["feed"]])                                        # one request, whatever the number of apartments

    def test_an_apartment_with_no_number_shown_takes_it_from_its_address(self):
        self.assertEqual([reader.unit_label(s) for s in ("2203-1236434", "56w-1713-1236434", "1812-431-")], ["2203", "56w-1713", "1812-431"])

    def test_a_community_with_nothing_available_reads_as_no_units(self):
        page = details("Crystal City Lofts", "305 10th St S, Arlington, VA 22202")
        self.assertEqual(reader.read(BUILDING, web({BUILDING["feed"]: page}))["units"], [])

    def test_a_page_that_is_not_the_community_is_not_answering(self):
        with self.assertRaises(NotAnswering):
            reader.read(BUILDING, web({BUILDING["feed"]: "<html><title>Just a moment...</title></html>"}))


class DweckDiscoveryTest(unittest.TestCase):
    def test_communities_come_from_the_sitemap_and_each_page_says_where_it_is(self):
        asked = []
        pages = {finder.SITEMAP: SITEMAP, "https://www.dweckproperties.com/communities/crystal-city-lofts/": LOFTS,
                 "https://www.dweckproperties.com/communities/far-away/": FAR}
        found = DISCOVERERS["dweck"](web(pages, asked))
        self.assertEqual(len(found), 1)                                                    # the one in Texas is left out
        b = found[0]
        self.assertEqual((b["id"], b["manager"], b["name"]), ("dweck-crystal-city-lofts", "Dweck", "Crystal City Lofts"))
        self.assertEqual(b["address"], {"street": "305 10th St S", "city": "Arlington", "state": "VA", "zip": "22202"})
        self.assertEqual((b["lat"], b["lon"]), (38.863824, -77.049522))
        self.assertEqual((b["platform"], b["feed"], b["url"]), ("dweck", BUILDING["feed"], BUILDING["feed"]))
        self.assertEqual(asked[0], finder.SITEMAP)
        self.assertNotIn("https://www.dweckproperties.com/communities/", asked)            # the list page itself is not a community

    def test_limit_and_a_page_that_cannot_be_read(self):
        pages = {finder.SITEMAP: SITEMAP, "https://www.dweckproperties.com/communities/far-away/": FAR}
        self.assertEqual(finder.discover(web(pages)), [])                                  # one gone, one out of the region
        asked = []
        finder.discover(web({finder.SITEMAP: SITEMAP}, asked), limit=1)
        self.assertEqual(len(asked), 2)


if __name__ == "__main__":
    unittest.main()
