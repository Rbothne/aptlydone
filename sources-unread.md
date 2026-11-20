# Buildings and companies this tracker cannot read yet

Every company the tracker reads is in `managers.json`; how each listing system is read is in `aptrack/readers/`.
**This file is for the rest**: what each source actually serves, which routes have been tried, what answered, and
what would open it next. Read it before probing a source again, and keep it current: a source that gets read moves
out; a verdict that turns out wrong is corrected in place, with its date.

The method is borrowed from the owner's shopping tracker (`stores-unread.md` there): **change route, don't push
harder**. A verdict below records a route that was tried, never a source that is beyond reading. Kettler was
"needs a key" for a night, and then its own search turned out to list every building's floor plans, with prices, in
one request.

## The rules

- Requests go out under the tracker's own name (`aptrack/fetch.py`), at its usual pace or slower. A site's
  `robots.txt` pace is kept (Dweck: five minutes).
- **A refusal closes that address, not the source.** HTTP 403, 429, a Cloudflare challenge ("Just a moment",
  `cf-mitigated: challenge`), a CAPTCHA: write down what answered and take the next route. Do not ask again harder,
  and do not ask many addresses of one service at once: on 2026-11-20 two reads that asked 61 RentCafe sites in
  the same second turned its check from refusing some requests to refusing all of them.
- **A refusal is never worked around.** No browser user-agent, no hidden automation, no proxies or borrowed
  addresses, no solving of bot checks. This is where this tracker and the shopping tracker part ways: a route
  that needs a disguise is not a route here.
- Terms of use: the owner accepted that risk for RentCafe sites, Kettler, Equity and Dweck (2026-11-20). That is a
  decision about terms, not about technical barriers.
- Nothing is typed in by hand. A route counts only if a script can follow it from a company's own pages.

## Routes, in the order to try them

1. **A listing system the building's website embeds.** SightMap unit maps, G5, Jonah, RentPress, AppFolio,
   schema.org offers: `discover/common.py` `recognise()` and `site_feed()` already look for these on up to seven
   pages of a building's site. A new system seen on several sites is worth a reader of its own.
2. **What the page already carries.** JSON-LD, data attributes on floor-plan cards, a JSON blob the page hands
   its own scripts. Test an extractor against a saved page before asking the site again.
3. **The company's own search or API.** *Reach for this early.* A company page that fills itself with a script
   is asking some address for a list; read the script, find the address and its parameters, and try the obvious
   neighbours of a parameter (`include_properties` had a sibling, `include_floorplans`). Kettler, JBG SMITH's
   building list and Mill Creek's list all come this way.
4. **The host the unit list is really built from.** Leasing portals, vendor APIs and widget hosts are often not
   the building's own host. Check each host's own `robots.txt` and what it answers; one refusing host says
   nothing about another.
5. **Sitemaps.** A sitemap of floor-plan or availability pages gives a count, and sometimes the whole list
   (Dweck: 669 availability pages; its community pages turned out to list the same apartments, one request each).
6. **The same building somewhere else.** The management company's page for the building, the owner's site, a
   sister site of the same development. A building is often listed in more than one place, at different detail.
7. **A feed published on purpose.** Rare for apartments; note it here if one is ever seen.

Listing sites (Apartments.com, Zillow, Rent.com and the like) are not a route: their terms forbid reading and they
are not the buildings' own sources.

## What has been tried

### RentCafe (Yardi) building sites: 61 buildings (JBG SMITH 17, Kettler's own-site route before 2026-11-20)

- **What they serve:** `/floorplans` lists floor plans with a price range each (`data-floorplan-*` attributes) and
  links to one page per plan; a plan's page lists each apartment (number, base rent, required monthly fees, lease
  length, date, a line of features). `readers/rentcafe.py` reads both layouts of the plan page (cards, table rows).
- **Their robots files allow** `/floorplans`.
- **What answered:** read one site at a time early on 2026-11-20, three JBG SMITH buildings came through whole
  (48 apartments). After two reads that asked every site at once, every request was refused
  (`403`, `cf-mitigated: challenge`), from a home connection and from GitHub's servers alike, and still was
  hours later at one request every two seconds.
- **Routes tried:** the building site (route 1, refused); the leasing host `*.securecafe.com` where "Apply Now"
  goes (route 4): `robots.txt` and both listing pages answer the same challenge. The official RentCafe API
  (`api.rentcafe.com`) needs a token each company holds; none is published on the sites seen.
- **Now:** read a sixth at a time every two hours (`spread.yml`), in case the check relents.
- **What would open it:** the check letting ordinary requests through again (watch the spread job's results for
  a week before concluding); or a company-level route like Kettler's for JBG SMITH (not found: see below).

### JBG SMITH: 19 buildings, 17 on RentCafe, 2 with no listing system found

- **Building list:** its sitemap plus `api-jbgsmith.reol.com/api/page/property/residential?id=N` (route 3): name,
  address, coordinates, the building's website. **No prices or availability in that record** (checked
  2026-11-20: `availabilities_url` is empty, no rent or floor-plan fields).
- **What would open it:** RentCafe relenting; or another address on `api-jbgsmith.reol.com` that lists
  availabilities (not looked for beyond the one record; the site's own scripts would name it).

### Kettler: 75 buildings in the tracked counties, 30 with prices (was 8 before 2026-11-20)

- **Read now:** its own search with `include_floorplans=1` (route 3) gives floor plans with a starting price and
  the number free, in one request: 26 buildings are read that way (23 with something free). 10 more have a unit
  map and are read from it.
- **Not read:** 32 buildings the search lists with no floor plans, whose own sites are RentCafe (refused), and 7
  that name no listing system.
- **Fixed 2026-11-20, takes effect at the next search:** Chase and Coda at Bryant St. failed on a unit-map
  address their sites print run together with another word (`4d7p16movkxaspx_MenuLink`); a map's name is eleven
  characters and is now cut back to it.
- **What would open more:** RentCafe relenting; the search starting to list floor plans for more buildings.

### Van Metre: 4 building sites linked from its home page

- **What answered:** the portfolio home page answered once and refused twice on 2026-11-20 (`403`); its list
  pages (`/va/apartments` and the like) refused every time. The building sites are RentCafe.
- **What would open it:** nothing found. Discovery stays on, weekly, and keeps what a good day shows.

### Bernstein Management

- **What answered:** `www.bmcproperties.com` refuses its home page (`403`); its robots file is RentCafe's
  standard one. No list of buildings could be read, so nothing is tracked.
- **Routes not yet tried:** whether the company publishes its buildings anywhere else it controls (a second
  domain, a careers or about page naming them with links). Listing sites name about 34 buildings around DC.

### Mill Creek: paused

- **Building list:** its WordPress API (`/wp-json/wp/v2/community`, route 3) works.
- **What answered:** the buildings' own sites answer with a Cloudflare challenge nearly every time.
- **Route 3 for prices, checked 2026-11-20:** a community's record in that API has no floor plans and no
  prices (its `number_of_homes_available` field is empty; the rest is marketing copy, amenities and photos).
- **What would open it:** the host its building sites load their unit lists from (route 4), not yet looked at.

### Greystar: 136 buildings, 130 with prices, no plain links left (2026-11-20)

- **The route that closed the gap (route 6):** Greystar's own page for a building
  (`www.greystar.com/<building>/p_<number>`) carries every free apartment in the data it hands its scripts
  (`"propertyUnits"`: number, square footage, floor, date, lowest rent and its lease length; `"floorplans"`;
  `"monthlyFees"`). It answers ordinary requests even where the building's own site (Entrata, RentCafe, a
  Cloudflare challenge) refuses. 22 buildings are read from it (`readers/greystar.py`); 110 from unit maps.
- **Worth knowing:** the search had been fetching these company pages all along, for the address. The prices
  were in a page already in hand.
- **Not read:** 6 buildings with nothing free or nothing in the page's data on the day.

### Paradigm, and Entrata sites generally

- **What answered:** Paradigm's building sites run on Entrata, which refused the tracker. Three Greystar Entrata
  sites (the Avana buildings) answered their home page with a Cloudflare challenge on 2026-11-20, so the host
  their unit lists load from could not even be seen. The Greystar ones are now read from Greystar's own pages.
- **Routes not yet tried for Paradigm:** its own company site's pages for each building (route 6, the move that
  worked for Greystar).

### RealPage online leasing

- Bayshore Landing (Willow Bridge): its leasing pages refused. Route 4 not tried.

### Daro, The Blairs, ROSS, Dittmar

- Daro's site refused every request. The Blairs' and ROSS's sites could not be connected to. No website was
  found for Dittmar. None has been tried twice; a second look on another day costs four requests.

### Buildings that are read but show no prices

- **WC Smith, 24 buildings:** its own data says nothing is available. Not a wall.
- **Bozzuto, 4 unit maps** (City Market at O, Ravensworth, Residences on The Avenue, The Metropolitan): the map
  lists every apartment with no price or date. **4 more** (Lumina, Radia, The Eliza, Carver Senior) publish no
  floor plans. Route 6 (the building's own site, or the owner's) has not been tried for these eight.
- **Willow Bridge, 9 plain links:** Cloudflare-challenged or RentCafe sites (Siena Park, Auden Place, Lincoln at
  Fair Oaks, Masonvale), pages the search cannot follow (Kiley's floor-plans link is broken; Park Place at Van
  Dorn is on Repli360), and three whose page on `willowbridgepc.com` gives each floor plan's beds, baths, square
  footage and a "Starting At" price but no count of apartments free (Lincoln Old Town, The Blake, Tribeca; seen
  on The Blake's page 2026-11-20: `class='plan-price'`). Reading those needs the page to show a floor plan whose
  count is unknown, which it cannot do yet. For the other six: does `willowbridgepc.com` have a page for each
  (route 6)?

## Still open, most promising first

1. Willow Bridge's company pages: a plan-level reader for the "Starting At" prices (needs the page to show a
   plan with an unknown count), and whether the other six links have a company page too.
2. Paradigm's and Mill Creek's own company pages for each building: the route that worked for Greystar.
3. JBG SMITH's API: an availabilities address.
4. The eight Bozzuto buildings by another door.
5. A second look at Daro, The Blairs, ROSS, and a search for Bernstein's building list.
