from fieldserver.core.coords import occurrence_coords

HOME = (40.0, -111.0)


def test_own_fix_wins():
    assert occurrence_coords({"latitude": 51.5, "longitude": -0.1}, *HOME) == (51.5, -0.1)


def test_a_named_region_is_not_the_home_ground():
    assert occurrence_coords({"region": "London"}, *HOME) == (None, None)


def test_no_place_at_all_falls_back_to_the_home_ground():
    assert occurrence_coords({"region": "  "}, *HOME) == HOME
    assert occurrence_coords({}, *HOME) == HOME


def test_no_home_ground_means_no_filter():
    assert occurrence_coords({}) == (None, None)


def test_the_home_region_by_name_keeps_the_home_ground():
    assert occurrence_coords({"region": "Utah, US"}, *HOME, fleet_region="Utah") == HOME
    assert occurrence_coords({"region": "London"}, *HOME, fleet_region="Utah") == (None, None)
