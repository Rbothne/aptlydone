import unittest

from aptrack import costs


def fee(label, amount, *, required=True, when="monthly", refundable=False, kind=None):
    return {"label": label, "type": kind, "category": None, "required": required, "when": when,
            "refundable": refundable, "amount": amount, "text": None if amount is None else f"${amount}"}


def unit(rent=2400, lease=12, fees=None, special=None):
    return {"rent": rent, "lease": lease, "fees": fees, "special": special}


AMENITY = fee("Amenity Fee - First Lease", 600.0, when="additional", kind="amenity")
DEPOSIT = fee("Security Deposit - Standard", 500.0, when="additional", refundable=True, kind="deposit")
APPLICATION = fee("Application Fee", 50.0, when="additional", kind="application")
PARKING = fee("Parking - Reserved", 225.0, required=False, when="optional", kind="assigned_parking")
MOTORCYCLE = fee("Parking - Motorcycle", 100.0, required=False, when="optional", kind="motorcycle_parking")
PET_RENT = fee("Pet Rent", None, required=False, when="optional", kind="pet_rent_other")


class FreeMonthsTests(unittest.TestCase):
    def test_digits(self):
        self.assertEqual(costs.free_months("1 month free"), 1)
        self.assertEqual(costs.free_months("Get 2 months free on select homes!"), 2)
        self.assertEqual(costs.free_months("1.5 months free"), 1.5)

    def test_words(self):
        self.assertEqual(costs.free_months("Move in by November 30th to enjoy two months free of base rent on select units"), 2)
        self.assertEqual(costs.free_months("One month free"), 1)
        self.assertEqual(costs.free_months("Half month free"), 0.5)
        self.assertEqual(costs.free_months("half a month free"), 0.5)

    def test_fraction(self):
        self.assertEqual(costs.free_months("1/2 month free"), 0.5)

    def test_weeks(self):
        self.assertAlmostEqual(costs.free_months("Up to 6 weeks free!"), 6 / 4.345, places=3)
        self.assertAlmostEqual(costs.free_months("six weeks free"), 6 / 4.345, places=3)

    def test_free_rent_wording(self):
        self.assertEqual(costs.free_months("Receive 2 months of free rent"), 2)
        self.assertEqual(costs.free_months("One month's rent free"), 1)

    def test_up_to_counts_as_the_number(self):
        self.assertEqual(costs.free_months("Up to 2 months free"), 2)

    def test_no_match(self):
        for text in (None, "", "Tour your way!", "Free parking for a year", "$500 off your first month", "Ask about our specials"):
            self.assertIsNone(costs.free_months(text), text)


class FeeTests(unittest.TestCase):
    def test_one_time_counts_required_nonrefundable_one_off_fees(self):
        self.assertEqual(costs.one_time([AMENITY, DEPOSIT, APPLICATION, PARKING, fee("Sewer", None), fee("Insurance", 12.0)]), 650.0)

    def test_one_time_skips_optional_and_deposits(self):
        optional = fee("Storage setup", 75.0, required=False, when="additional")
        named_deposit = fee("Holding Deposit", 300.0, when="additional")
        self.assertEqual(costs.one_time([optional, named_deposit, DEPOSIT]), 0)

    def test_parking_from_is_the_lowest_car_space(self):
        garage = fee("Parking - Garage", 160.0, required=False, when="optional", kind="garage_parking")
        self.assertEqual(costs.parking_from([PARKING, MOTORCYCLE, garage]), 160.0)
        self.assertIsNone(costs.parking_from([MOTORCYCLE, AMENITY]))

    def test_pets_allowed(self):
        self.assertIs(costs.pets_allowed([PET_RENT]), True)
        self.assertIsNone(costs.pets_allowed([AMENITY]))


class TrueMonthlyTests(unittest.TestCase):
    def test_plain_rent(self):
        self.assertEqual(costs.true_monthly(unit(), []), 2400)

    def test_one_month_free_on_twelve(self):
        self.assertEqual(costs.true_monthly(unit(special="1 month free"), []), 2200)

    def test_monthly_fees_added(self):
        self.assertEqual(costs.true_monthly(unit(fees=100, special="1 month free"), []), 2300)

    def test_one_time_fee_spread_over_the_lease(self):
        self.assertEqual(costs.true_monthly(unit(fees=100, special="1 month free"), [AMENITY, DEPOSIT]), 2350)

    def test_fifteen_month_lease(self):
        self.assertEqual(costs.true_monthly(unit(rent=3000, lease=15, special="1 month free"), []), 2800)

    def test_explicit_special_overrides_the_units_own(self):
        self.assertEqual(costs.true_monthly(unit(), [], special="2 months free"), 2000)

    def test_unparsed_special_changes_nothing(self):
        self.assertEqual(costs.true_monthly(unit(special="Ask about our specials"), []), 2400)

    def test_missing_lease_defaults_to_twelve_without_a_concession(self):
        self.assertEqual(costs.true_monthly(unit(lease=None), [AMENITY]), 2450)

    def test_missing_lease_with_a_concession_is_unknown(self):
        self.assertIsNone(costs.true_monthly(unit(lease=None, special="1 month free"), []))

    def test_concession_longer_than_the_lease_is_unknown(self):
        self.assertIsNone(costs.true_monthly(unit(lease=3, special="6 months free"), []))
        self.assertIsNone(costs.true_monthly(unit(lease=2, special="2 months free"), []))

    def test_result_is_whole_dollars(self):
        self.assertEqual(costs.true_monthly(unit(rent=2333, fees=12.36, special="6 weeks free"), []), round(2333 * (12 - 6 / 4.345) / 12 + 12.36))


class ApplyTests(unittest.TestCase):
    def test_building_offer_gives_an_if_it_applies_figure(self):
        u = unit(fees=100)
        costs.apply(u, [AMENITY], "Two months free on select units")
        self.assertEqual((u["true"], u["true_offer"]), (2550, 2150))

    def test_units_own_special_is_the_main_figure(self):
        u = unit(special="1 month free")
        costs.apply(u, [], "Two months free on select units")
        self.assertEqual((u["true"], u["true_offer"]), (2200, None))

    def test_no_offer_or_unparsed_offer(self):
        u = unit()
        costs.apply(u, [], None)
        self.assertEqual((u["true"], u["true_offer"]), (2400, None))
        costs.apply(u, [], "Ask about our specials")
        self.assertEqual((u["true"], u["true_offer"]), (2400, None))


if __name__ == "__main__":
    unittest.main()
