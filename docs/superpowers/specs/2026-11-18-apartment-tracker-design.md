# Apartment tracker: design

Date: 2026-11-18. Status: revised after the owner's first review; awaiting approval.

Lines marked **(call)** are choices made while writing this up, not things the owner asked for. They are open to correction.

## 1. Intent

A personal website for apartment hunting across the DC, Maryland and Virginia region. It follows individual units at professionally managed buildings, records every price change from the day tracking starts, and points out units priced unusually low for their floor plan, building and surroundings. Around each unit it shows what the owner needs to judge it: size, layout, building tier, in-unit laundry, parking, rating, nearby crime, area demographics and the commute to work.

Why: listing sites show "from $X" ranges that lag the buildings' own sites, and nobody publishes unit price history. Managed buildings reprice units daily with pricing software, and that is where mispriced units appear. Reading the buildings' own sites every day gives the owner a view the listing sites do not offer.

The owner is the only user for now and wants to use it again for next year's search. It should be built so that more users could be added later without a major rewrite.

## 2. Goals, non-goals, anti-goals

**Goals**

- Track available units at managed buildings: rent, sqft, beds, baths, floor plan, floor, available date, concessions, fees.
- Cover the whole region. Every listing the readers can reach is collected; nothing is limited to chosen neighborhoods. Each user marks their own no-go regions in the page.
- Everything is automated. Buildings are found, located and described by scripts. A fact that cannot be collected automatically is left blank; nothing is typed in by hand.
- Keep price history from the first run, and keep it long enough to serve next year's search (a year of history shows the seasonal low).
- Give each unit a Deal label (Steal, Good, Normal, High) with the reason written on the card.
- Show area context: crime near the building, census demographics, the ZIP code's rent trend, commute times.
- Ask a few setup questions (work location, budget or income, size, must-haves, priorities) and rank units by fit.
- Run for free on GitHub Actions and GitHub Pages, like the owner's existing wishlist site.
- Start collecting history as early as possible. Tracking goes live before the page is finished.

**Non-goals for the first version**

- Accounts, saved searches on a server, price alerts.
- The cloud function for commute lookups (see section 4).
- Private listings (basements, rooms, owner-listed condos) and condos listed by agents. The data format leaves room for them.
- A chat assistant. The wishlist site's one can be ported later.
- Route maps and named traffic chokepoints. The first version shows rush-hour and off-peak minutes.
- Transit commutes.

**Anti-goals** (failures even if everything technically works)

- Calling a unit a steal when the low number is a teaser: a concession that vanishes at renewal, or mandatory fees left out.
- A bad run silently replacing good price history.
- Getting blocked by hammering building sites.
- Needing a major refactor to add users later.
- Any per-building or per-area fact that someone has to type in or keep up by hand.
- Race or any other demographic figure feeding the Deal or Match scores. Demographics are displayed, never scored.

## 3. Constraints

- No servers and no paid services. One optional key (Google, within its free allowance) for commute and ratings.
- Build scripts use the Python standard library only, as the wishlist site does.
- The page is plain HTML and JavaScript with no build step. A map library (Leaflet) is bundled into the repository the way the wishlist site bundles its one library.
- The owner's work address, income, no-go regions and other setup answers stay in the browser. They never go into the repository. The work address is sent only to the routing service.
- The repository is public but the site is for personal use. Demographics, including race, sit behind one Settings switch that is on by default.
- Windows development machine; Python is run as `py`.

## 4. Approaches

**Where listings come from**

| Approach | Trade-off | Decision |
|---|---|---|
| Read each building's own site | Freshest unit-level prices; one reader per listing system covers many buildings; misses private listings | **Picked** |
| Scrape Apartments.com or Zillow | Covers everything, but blocked hard, against their terms, and prices are stale ranges | Rejected |
| Paid listings API | Simple, but costs money and gives little unit-level detail | Rejected |

**Foundation**

| Approach | Trade-off | Decision |
|---|---|---|
| 1. Static site: scheduled job writes data files, GitHub Pages serves them, setup answers live in the browser | Free, no servers, proven by the wishlist site. Commute needs a key the user pastes in | **Picked** |
| 2. Option 1 plus a small cloud function that holds the routing key | Any visitor gets commute numbers with no setup; one more thing to deploy | Deferred. Option 1 is built so this bolts on |
| 3. Full app with a database and accounts | Multi-user from day one; costs money and upkeep | Rejected until there are real users |

Three seams keep option 2 or 3 from needing a rewrite:

1. **Commute** goes through one function in the page. Pointing it at a cloud function later changes one address.
2. **Setup answers** live in one profile object in browser storage. An account system would sync that object.
3. **Units** from every reader use one common format (section 6), and the page loads data through one loader.

## 5. What was tested

Run on 2026-11-18 from the owner's home connection with a plain script (no browser):

| What | Result |
|---|---|
| SightMap unit-map feed (used by Bozzuto; also seen at WC Smith) | Confirmed. `https://sightmap.com/embed/<id>` contains the address of a JSON feed, `https://sightmap.com/app/api/v1/<asset>/sightmaps/<n>`. For 5333 Connecticut it returned 15 units (`unit_number`, `area`, `price`, `total_price`, `available_on`, `floor_plan_id`, `specials_description`, `display_lease_term`) and 44 floor plans (`name`, `bedroom_count`, `bathroom_count`). The response is gzip-compressed |
| Fees and amenities in the same feed | Confirmed. `expenses` lists each fee with a type and whether it is required (reserved parking, pet rent, amenity fee, utilities), with amounts per unit in `expense_amounts`. `amenities` lists titled amenities (Concierge, Pool, Fitness Center, Rooftop Bar, Dog Run and so on) |
| Building location | Confirmed for Bozzuto. The building page carries structured data with the street address, ZIP code, latitude and longitude. It has no year built, rating or laundry field |
| Finding buildings automatically | Confirmed for Bozzuto: its sitemap lists 187 buildings in DC (64), Maryland (62) and Virginia (61). Camden's sitemap has a file of available-apartment pages; not yet read |
| Camden | Confirmed. `/apartments/<city>/<building>/available-apartments` embeds 79 unit records (`unitNumber`, `floorNumber`, `squareFeet`, `monthlyRent`, `moveInDate`, `leaseTerm`). Where beds and baths sit in that page was not checked |
| Site rules (`robots.txt`) | Bozzuto allows its pages and disallows `/api/` and `/search`. Camden allows everything. SightMap disallows only `/manage` and `/auth`. The readers stay inside these |
| Avalon | Loads with `squareFeet` and `availableDate` fields. Prices not confirmed |
| Equity | Loads with unit-availability structures. Prices not confirmed |
| WC Smith, Gates Hudson | Use RentCafe. Prices not in the plain page |
| Keener | Uses AppFolio. Listings not checked |
| Daro | Blocked by Cloudflare |
| UDR, Dittmar, Bernstein, UIP, Kettler, JBG Smith | Guessed addresses failed. Untested |

**Not tested:** whether GitHub's servers get the same answers as a home connection. This is the first thing the build must check. If GitHub is blocked, the same script runs on the owner's PC on a schedule (Windows Task Scheduler) and pushes the data; nothing else changes.

**Not verified:** the exact addresses and field names of the crime, census, property-record, boundary, neighborhood-name, rent-trend, routing and ratings sources in sections 6, 8 and 9.

## 6. Data

### The only hand-kept file

`managers.json` lists management companies' websites, one line each (`{"site": "bozzuto.com", "platform": "sightmap"}`), plus settings. It plays the part `stores.json` plays in the wishlist site. Adding a company adds all its buildings. Nothing about an individual building or area is ever typed in.

Settings include the list of counties that count as the region **(call)**: DC; Arlington, Alexandria, Fairfax, Falls Church, Loudoun and Prince William in Virginia; Montgomery, Prince George's, Howard and Anne Arundel in Maryland. Howard and Anne Arundel are included because the owner works there. Buildings outside the list are ignored; widening the region is one edit.

### Buildings (generated)

A discovery job produces `buildings.json`. For each company it:

1. Reads the company's sitemap to list its building pages.
2. Reads each building page for its name, address, coordinates (structured data) and listing-system id (for example the SightMap embed address).
3. Looks up the census tract and county from the coordinates (Census geocoder) and drops buildings outside the region.
4. Looks up a neighborhood name from OpenStreetMap's reverse lookup, for display.

It runs weekly, so new buildings appear and closed ones drop out without anyone editing a file.

A second discovery source to try **(call)**: OpenStreetMap's apartment buildings that carry a website, each checked for a listing system the readers know. This finds buildings whose company is not in `managers.json`.

A building whose site cannot be read still appears as a plain link card with whatever was collected.

### Building facts (all derived; blank when not available)

| Fact | Where it comes from |
|---|---|
| Parking and its monthly cost | The feed's fee list (confirmed for SightMap) |
| Pets allowed, pet rent | The feed's fee list |
| Mandatory monthly fees | The feed's fee list, required items only |
| Amenities | The feed's amenity list and the building page |
| In-unit laundry | Keywords ("washer", "in-unit", "in-home") in amenities, floor-plan and unit descriptions, and the building's pages. Values: in-unit, shared, unknown |
| Tier: Luxury or Standard | Computed: Luxury when the building has two or more premium amenities (concierge, pool, rooftop, doorman) or its rent per sqft is in the top third of buildings within a mile. `Private` is reserved for private listings later |
| Year built | Public property records, one reader per jurisdiction, starting with DC and Maryland. Blank where no open record exists |
| Rating | Google's rating and review count, matched by name and address. Blank when no key is set |

### Regions

No neighborhoods are defined by hand. Two automatic layers cover the whole region:

- **Census tract:** the unit for demographics and for crime rates.
- **ZIP code:** the unit for the rent trend, for commute lookups and for no-go regions. Boundaries come from the Census Bureau's public map service, fetched by a script.

Cards show the neighborhood name from OpenStreetMap alongside the ZIP code.

### Common unit format (written by every reader)

```
id          "<building id>:<unit number>"
building    building id
unit, floor
plan        floor plan name
beds, baths, sqft
rent        monthly base rent as quoted
fees        required monthly fees with fixed amounts, when the source gives them
lease       lease length in months the quote is for, when given
available   date
special     raw concession text, when given
notes       unit-level description text, when given (searched for laundry and similar)
url
```

Each reader also returns the building-level fee list and amenity list when its source has them.

### Price history (`state.json`)

- Per unit: first seen, last seen, and a point each time the rent changes. A unit missing from a successful read is marked gone on that day, keeping its last price and days listed. A unit number that comes back later starts a new listing.
- Per floor plan per building: the lowest and median rent each day it changes. Units come and go but floor plans persist, so this is the series that makes next year's search useful. It is kept indefinitely. Unit records are kept for at least 400 days **(call)**.
- A building whose read fails keeps its previous units, marked stale. Nothing is marked gone on a failed read.

### Storage and size

Storage follows the wishlist site: a `data` branch holding the latest files as a single commit that each run replaces, with a check that refuses to save when the new history is under 80% of the old one. Added **(call)**: a monthly dated copy on its own branch, since this history has to survive a year.

The whole region could reach a few thousand buildings and tens of thousands of units. The page's data is therefore split into one file per county, and the page loads only counties that are not entirely no-go.

## 7. Scores

**Net effective rent.** Concessions are parsed from the text with patterns ("N months free", "N weeks free", "$X off"). Net rent = rent × (lease months − free months) ÷ lease months. Text that no pattern matches is shown as written and marked "not counted" **(call: patterns only, no AI parsing)**.

**All-in monthly cost** = net rent + required monthly fees with fixed amounts + the building's parking cost when the profile says parking is needed.

**Deal** is worked out by the build script and is the same for everyone. It combines:

1. **Against its own floor plan's history:** where today's net rent sits in the tracked range for that floor plan in that building. Pulled toward the middle while history is short, the way the wishlist site's `SHRINK` works.
2. **Against identical units now:** this unit's rent against the median for the same floor plan in the building today.
3. **Against comparable units nearby:** same bed count, sqft within 15%, same tier, within one mile. Percent below the median net rent of at least five comparables; if there are fewer, widen to two and then three miles, and if there are still too few, give no score.

Labels: Steal, Good, Normal, High. Starting rule **(call)**: Steal means at least 12% under comparables and at or near the floor plan's lowest tracked price (or history under 30 days). The thresholds are named constants the owner can tune.

Every card states the reason in words, for example "11% under 14 similar units within 1 mile · lowest in 41 days tracked · 1.5 months free counted".

**Renewal risk** guards against teasers:

- When the net rent depends on a concession, the card says "Renewal: likely back to $X" (the sticker rent).
- A DC building with a known year built before 1976 shows "Renewal: likely capped (rent control)". This is a rule of thumb, labelled "likely", and shown only where the year is known.

**Match** is worked out in the page from the profile.

- Hard filters: beds, minimum sqft, move-in window, must-haves, maximum budget, no-go regions.
- Weighted parts, using the "matters most" sliders: price (all-in cost against budget), commute (weekly minutes = (morning + evening) × days onsite), safety (crime near the building), size.
- Income, when given, flags units where monthly income is under three times the rent as "may not qualify".
- A must-have that is unknown for a building (laundry, say) does not hide the unit by default; the card says "laundry unknown" and a switch hides unknowns.

**Top picks**, the default sort, blends Deal and Match. Weights live in one scoring file, as `score()` does in the wishlist site.

## 8. Area data

Refreshed on a slower schedule than units: crime weekly, the rest monthly.

- **Crime:** open incident data, one reader per jurisdiction, starting with DC, Montgomery County and Arlington County and extending to the other counties where incident-level data is published. Each incident is sorted into violent or property. Shown per building as counts within half a mile over the last 12 months, and per tract as a rate per 1,000 residents. Where a county publishes nothing usable, the card says "no crime data". Categories differ between jurisdictions, so cross-border comparisons are approximate and the page says so.
- **Demographics:** Census ACS 5-year figures per tract, the same source everywhere: population, median household income, median age, share with a degree, race and ethnicity, median rent, share renting. One Settings switch hides the panel.
- **Rent trend:** Zillow's published rent index by ZIP code, which goes back years. This gives every ZIP a trend and a seasonal pattern from day one, before the site's own history builds up.
- **Ratings:** see the building facts table.

## 9. Commute

- One function in the page takes the profile and returns minutes per ZIP code for three trips: morning, evening and off-peak.
- It calls Google's route matrix service with predicted traffic for the next ordinary weekday at the profile's hours, using a key pasted into Settings and kept in the browser **(call: Google, because it predicts traffic for a chosen time)**.
- Lookups cover only ZIP codes that have buildings and are not no-go, and are cached in the browser. With around 200 such ZIP codes that is about 600 lookups per work location, inside Google's free monthly allowance of 5,000 (assuming traffic lookups bill at that tier). A starred building gets an exact lookup on demand.
- With no key, the page shows straight-line distance and says so.

## 10. The page

**Setup screen**, shown on first visit; every field can be skipped and edited later in Settings:

```
Work address [____________]  Onsite [3] days/wk  Leave [8:00]  Return [5:30]
Budget [$____/mo]   or   Income [$____/yr]
Beds [1] [2]     Min sqft [700]     Move in [from] – [to]
Must have   [x] In-unit washer/dryer   [x] Parking   [ ] Pets
Matters most   Price ▮▮▮▮▯  Commute ▮▮▯▯▯  Safety ▮▮▮▮▮  Size ▮▮▮▯▯
No-go regions  [ open map ]
```

**No-go regions**

- A map of the region divided into ZIP codes. Clicking a ZIP code toggles it no-go; a switch per county turns a whole county off or on.
- The map can be coloured by violent crime, median rent, median income or commute, so the choice is made with the numbers in view.
- Any card's menu has "No-go this ZIP code", with Undo.
- No-go regions hide listings in the page only. The build always collects everything.

**Tabs**

- **Units:** Followed (starred) and Everything. A starred unit that gets leased stays, showing its last price, the date and days listed.
- **Buildings:** one row per building with its available units, typical prices, tier, rating and facts.
- **Map:** the same ZIP-code map, with buildings as points and the colouring options above. This answers "which parts of the region are worth looking at".

**Unit card**

```
STEAL   5333 Connecticut · #215          Chevy Chase · 20015
1 bed · 1 bath · 827 sqft · floor 2 · available Nov 29
$2,700/mo ($3.26/sqft)     all-in $2,950 with parking and fees
▁▂▂▁▁▃●  lowest in 41 days tracked
11% under 14 similar units within 1 mile · typical for this plan $2,950
Commute 38 / 52 min (morning / evening) · Within ½ mile: 3 violent, 41 property (12 mo)
Luxury · in-unit laundry · parking $225 · pets · ★ 4.3 (212)
Renewal: likely back to $2,950
```

(The figures in the sketch are made up, apart from the unit's rent and size and the parking fee.)

**Filters:** county, ZIP code, beds, sqft, rent, laundry, parking, tier, manager, available by, Deal label. Buildings and managers can be marked "not interested".

**Sorts:** Top picks, Deal, Match, price, price per sqft, commute, newest, biggest price drop.

Carried over from the wishlist site: stars, the Settings panel, backup and restore of browser data, the "updated N hours ago" line, the price-history chart on cards.

## 11. Running it

- **Units:** twice a day **(call)**, early morning after buildings push new prices and again in the evening. One request per second per site at most, a few sites at a time, and a site that answers "too many requests" is skipped and retried at the end, as the wishlist build does.
- **Discovery:** weekly.
- **Area data:** crime weekly; census, boundaries, rent trend, property records and ratings monthly.
- **Layout (call):** a new repository in this folder, not a branch of the wishlist site. It copies the wishlist site's patterns (workflow, data branch, fetch-with-retry, history recording, percentile ranking, browser backup). The served page lives in `site/` so this `docs/` folder is not published.

## 12. Order of work

1. Check that GitHub's servers can read one SightMap feed and one Camden page. If not, set up the scheduled run on the owner's PC.
2. Tracking: discovery for Bozzuto and Camden across the region, the two readers, history, the scheduled job. History starts accumulating here.
3. The page: unit list, filters, cards, history chart, stars.
4. Net effective rent, fees, building facts, Deal score and labels.
5. Area data (census, crime for the first three jurisdictions, rent trend), ZIP boundaries, the map and no-go regions.
6. Setup screen, commute, Match score.
7. More readers and companies, in this order of promise: Avalon, Equity, RentCafe, AppFolio, then the untested managers. More crime and property-record readers. Ratings. The OpenStreetMap discovery source.

## 13. Testing

- Each reader separates fetching from parsing, and parsing is tested against saved sample responses.
- Discovery, fact derivation (laundry keywords, tier, fees), history rules (changed, gone, returned, failed read) and the Deal calculation are tested with small made-up data.
- Scoring in the page is kept as pure functions so it can be tested the same way.

## 14. Left to the builder

- File and module layout inside the build scripts and the page.
- Exact weights and thresholds, starting from the values above.
- How each crime category maps to violent or property.
- The keyword lists for laundry and premium amenities.
- The look of the page, starting from the wishlist site's.
- How the per-county data files are compacted.

## 15. Revisions after the first live run (2026-11-18)

Decided with the owner after the first full read (181 buildings, 4,502 units). Where this section disagrees with sections 6, 7 or 10, this section wins.

### True monthly cost

One number per unit, used everywhere a price is compared:

- rent spread over the lease after free months or weeks,
- plus required monthly fees with fixed amounts,
- plus required one-time fees (an amenity fee, say) spread over the lease.

A concession stated for the whole building ("two months free on select units") cannot be pinned to a unit. The card shows the true monthly cost without it, and an "if the offer applies" figure beside it. Parking stays a separate, optional add-on using the lowest listed price ("from $X").

The lease term is noted on the card and never disqualifies a unit.

### Three tags replace Steal / Good / Normal / High

All compare true monthly cost per sqft against units with the same bed count.

| Tag | Rule | Units on day one |
|---|---|---|
| BUILDING STEAL | 15% or more below similar units (size within 20%, at least three of them) in the same building | 58 of 4,054 scored |
| LOCAL VALUE | 20% or more below similar units (size within 15%) in other buildings within one mile, widening to two; needs five units from three buildings | 143 of 2,725 scored |
| ABSOLUTE STEAL | 10% or more below its own building and 15% or more below neighbors | 42 |

- Thresholds are named constants. The owner approved these as a starting point.
- A unit never compares against itself, and neighbors never include its own building.
- Once a floor plan has 30 days of history, ABSOLUTE STEAL also requires the unit to be within 3% of that plan's lowest tracked true monthly cost **(call)**.
- Excluded from tags and from everyone else's comparisons: income-restricted units, senior housing, and rooms rented singly (under 300 sqft).

### Income-restricted units

Flagged from the feed's affordable-housing field where present, otherwise from the floor-plan name (ADU, WDU, MPDU, IZ, "affordable", "workforce"). Hidden by default, with a switch. Where a source states an income cap, the page compares it with the income in the profile; no source read so far states one.

### "Fancy"

The Luxury / Standard tier from section 6 is dropped. Each building gets a rank instead: its one-bedroom rent per sqft against buildings within two miles **(call, to be checked against the buildings the owner named once their managers are covered)**.

### More facts, all from pages already being read

- Bozzuto building page, read daily: building-wide concession text, rating and review count, the manager's own neighborhood name, "coming soon" and "under construction" flags, the unit-feature list (source for in-unit laundry).
- SightMap feed: income-restricted flag, floor-plan drawing address, one-time fees.
- Camden: floor-plan drawing address; amenity lists from the building's home page.
- Google ratings are no longer needed for buildings whose manager publishes a rating.
- Price points are `[day, rent, special, lease, fees]`, and each building's concession text is kept as its own dated series, so true monthly cost can be recomputed for any past day.

### The page

- **Buildings first.** The main list is buildings, each showing its five best units for the current filters, with "show all N". Starred units still appear as unit cards under Followed.
- **Stars** work on a unit, or on a building with criteria ("any one-bedroom of 700+ sqft under $X").
- **Filters, not setup gates:** move-in date and budget are ordinary filters. Crime and maximum commute are sliders.
- **Region:** the whole region shows by default; no-go ZIP codes remove areas.
- **Floor filter:** a lowest and highest floor, with a one-click "ground floor only". Ground floor means floor 0 or 1 **(call)**; 98% of units state their floor.
- **Floor-plan drawings** appear on unit cards.
- **Honesty:** a building that publishes no prices says so; a unit is "no longer listed", never "leased"; every price shows when it was read.
- **First screen:** left open until the owner has used the first version.

### Running it

- A run in which more than a fifth of buildings fail ends in failure, so GitHub emails the owner **(call: the threshold)**.
- Four Bozzuto buildings publish unit maps without prices; they are listed as "no prices published".

## 16. Later the same day: what changed again

- **More companies.** Windsor, Willow Bridge and Greystar are discovered alongside Bozzuto and Camden. All use SightMap unit maps where a map exists; a building without one is a plain link. Windsor is discovered through its regional location pages, because reading every building nationwide made its site stop answering properly.
- **Census figures need no key.** They come through Census Reporter (the Census Bureau's own API now requires a key).
- **Crime** is counted within half a mile over 12 months for DC and Montgomery County. Other counties show "No crime data for this county" until a reader is written for them.
- **ZIP codes** come from the map lookup at discovery. A ZIP from a manager's page is believed only if it starts with 2, since some put the street number there.
- **Commute, first version.** No key: the work address is turned into coordinates by OpenStreetMap's Nominatim and timed by the public OSRM server, both called from the browser. Times ignore traffic and say so. Rush-hour times through a Google key remain a later option.
- **Map view.** A tab showing each matching building as a dot coloured by its best tag, with the work place marked.
- **No-go regions, first version.** A ZIP code is marked no-go from any building card or map popup and hidden everywhere until removed. Clicking ZIP areas on the map is still to come.
- **More filters:** minimum rating, managed by, violent crime nearby (slider), maximum drive (slider).

## 17. Decisions made while the owner was away (2026-11-18, afternoon)

The owner asked for these to be decided and published without check-ins; each is also listed in plain language in `site/changelog.html`.

- **Companies:** AvalonBay (its own reader; promotions are attached to the units they apply to, so they count in the true monthly cost) and WC Smith (a RentPress site, which prices per floor plan: one entry per available floor plan, with a count). Seven companies in all.
- **Crime:** readers for Prince George's and Fairfax counties, and Arlington for the last year it published locations (mid-2021 to mid-2022, labelled as such). No open incident data with locations was found for Alexandria, Howard, Loudoun, Anne Arundel, Prince William, Falls Church or Manassas Park.
- **Check price:** a unit 30% or more under similar units in its own building, or 40% or more under similar units nearby, is tagged "check", never a steal. Constants `SUSPECT_OWN` and `SUSPECT_LOCAL` in `deals.py`.
- **Income-restricted buildings:** in DC, a building standing on a completed project in the city's affordable-housing list where at least half the units are affordable is treated as income-restricted. Any match shows the city's unit counts on the building.
- **"High-end for its area"** is the label for a building whose one-bedroom cost per sqft is in the top third of buildings within two miles. The three buildings the owner named (The Earl, The Wendy, Windsor Courthouse) rank at 89, 78 and 96.
- **Following a building** remembers the bedroom, size and price filters in force at that moment and shows what fits them each day.
- **First-visit setup** asks for bedrooms, size, budget, move-in date, work address, longest drive and income. Income only drives a "needs income of $X" note (rent above a third of monthly income).
- **Sturdiness:** a site that stops answering is left alone after three failures in a row and come back to once, at the default speed; the same for a manager's facts pages and for discovery; a company that suddenly lists under half its buildings is not believed.
- **Speed:** SightMap and Bozzuto are read at four requests a second after a ramp test; everything else stays at one.
