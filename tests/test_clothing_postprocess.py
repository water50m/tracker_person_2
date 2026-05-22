from services.clothing_postprocess import FinalOutfitVoter, StableClothingVoter, select_clothing_items


def classes(items):
    return [item.class_name for item in items]


def test_skirt_multiplier_beats_dress_noise():
    selection = select_clothing_items(
        [
            ("dress", 0.80, None),
            ("skirt", 0.30, None),
            ("short_sleeve", 0.70, None),
        ]
    )

    assert classes(selection.items) == ["short_sleeve", "skirt"]


def test_dress_does_not_pair_with_weak_top_or_skirt():
    selection = select_clothing_items(
        [
            ("dress", 0.82, None),
            ("short_sleeve", 0.60, None),
            ("skirt", 0.20, None),
        ]
    )

    assert classes(selection.items) == ["dress"]


def test_dress_can_pair_with_strong_top_or_trousers_only():
    top_selection = select_clothing_items(
        [
            ("dress", 0.90, None),
            ("short_sleeve", 0.80, None),
            ("shorts", 0.30, None),
        ]
    )
    trousers_selection = select_clothing_items(
        [
            ("dress", 0.90, None),
            ("trousers", 0.72, None),
            ("skirt", 0.20, None),
        ]
    )

    assert classes(top_selection.items) == ["short_sleeve", "dress"]
    assert classes(trousers_selection.items) == ["dress", "trousers"]


def test_stable_vote_never_outputs_dress_with_skirt():
    voter = StableClothingVoter()
    stable = None
    for _ in range(5):
        stable = voter.update(1, select_clothing_items([("dress", 0.90, None)]).items)
    for _ in range(2):
        stable = voter.update(1, select_clothing_items([("skirt", 0.50, None)]).items)

    assert stable is not None
    assert stable.classes == ["dress"]


def test_final_vote_counts_dress_only_as_no_companion():
    voter = FinalOutfitVoter()
    for frame in range(10):
        voter.record(1, frame, select_clothing_items([("dress", 0.90, None)]).items)
    for frame in range(10, 13):
        voter.record(1, frame, select_clothing_items([("dress", 0.88, None), ("short_sleeve", 0.80, None)]).items)

    outfit = voter.summary()["tracks"]["1"]

    assert outfit["classes"] == ["dress"]
