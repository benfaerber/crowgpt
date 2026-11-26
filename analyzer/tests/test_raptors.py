"""Taxonomic raptor co-detections and their confidence gate (experiment 0121).

BirdNET runs on every recording and previously dropped every non-corvid
detection. Keeping true raptors above 0.70 is free, surfaces co-detections
honestly, and must never trip on English substring look-alikes like Common
Nighthawk (0.72 on capture 69) or Fowler's Toad (`fowleri`).
"""

from analyzer.birdnet import RAPTOR_MIN_CONF, _summarize_raptors, raptor_name


def test_raptor_threshold_is_strict_enough_to_resist_jay_mimicry():
    assert RAPTOR_MIN_CONF >= 0.70


def test_true_raptors_match_across_orders():
    assert raptor_name({
        "common_name": "Cooper's Hawk",
        "scientific_name": "Accipiter cooperii",
    }) == "Cooper's Hawk"
    assert raptor_name({
        "common_name": "Cooper's Hawk",
        "scientific_name": "Astur cooperii",
    }) == "Cooper's Hawk"
    assert raptor_name({
        "common_name": "Red-tailed Hawk",
        "scientific_name": "Buteo jamaicensis",
    }) == "Red-tailed Hawk"
    assert raptor_name({
        "common_name": "Great Horned Owl",
        "scientific_name": "Bubo virginianus",
    }) == "Great Horned Owl"
    assert raptor_name({
        "common_name": "Peregrine Falcon",
        "scientific_name": "Falco peregrinus",
    }) == "Peregrine Falcon"
    assert raptor_name({
        "common_name": "Osprey",
        "scientific_name": "Pandion haliaetus",
    }) == "Osprey"
    assert raptor_name({
        "common_name": "Turkey Vulture",
        "scientific_name": "Cathartes aura",
    }) == "Turkey Vulture"


def test_english_substring_impostors_are_refused():
    """Capture 69 scored Common Nighthawk at 0.72; BirdNET also has `fowleri`,
    `cowled`, `Howler`, `Junglefowl`, and `Hawk-Cuckoo`."""
    impostors = [
        ("Common Nighthawk", "Chordeiles minor"),
        ("Lesser Nighthawk", "Chordeiles acutipennis"),
        ("Australian Owlet-nightjar", "Aegotheles cristatus"),
        ("Dark Hawk-Cuckoo", "Hierococcyx bocki"),
        ("Great Lizard-Cuckoo", "Coccyzus merlini"),
        ("Fowler's Toad", "Anaxyrus fowleri"),
        ("Mexican Black Howler Monkey", "Alouatta pigra"),
        ("Black-cowled Oriole", "Icterus prosthemelas"),
        ("Red Junglefowl", "Gallus gallus"),
        ("American Crow", "Corvus brachyrhynchos"),
        ("Blue Jay", "Cyanocitta cristata"),
    ]
    for common, sci in impostors:
        assert raptor_name({"common_name": common, "scientific_name": sci}) is None, common


def test_common_name_fallback_works_without_scientific_name():
    assert raptor_name({"common_name": "Cooper's Hawk"}) == "Cooper's Hawk"
    assert raptor_name({"common_name": "Common Nighthawk"}) is None
    assert raptor_name({"common_name": "Black-cowled Oriole"}) is None


def test_summarize_raptors_deduplicates_and_keeps_peak_confidence():
    summary = _summarize_raptors([
        {"species": "Cooper's Hawk", "scientific_name": "Accipiter cooperii",
         "conf": 0.71, "start": 3.0, "end": 6.0},
        {"species": "Cooper's Hawk", "scientific_name": "Accipiter cooperii",
         "conf": 0.8424, "start": 12.0, "end": 15.0},
        {"species": "Great Horned Owl", "scientific_name": "Bubo virginianus",
         "conf": 0.76, "start": 0.0, "end": 3.0},
    ])
    assert summary == [
        {
            "species": "Cooper's Hawk",
            "scientific_name": "Accipiter cooperii",
            "confidence": 0.842,
            "start": 12.0,
            "end": 15.0,
        },
        {
            "species": "Great Horned Owl",
            "scientific_name": "Bubo virginianus",
            "confidence": 0.76,
            "start": 0.0,
            "end": 3.0,
        },
    ]
