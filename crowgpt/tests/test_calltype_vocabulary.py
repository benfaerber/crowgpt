"""The generator's call-type vocabulary, and the fleet's, kept honest.

crowgpt asks for a call type with a prefix token, and the token ids come from
`CORE`'s order. So the list is not a description — it is baked into every
checkpoint under results/, and moving an entry re-points a trained model at the
wrong class without changing a single number in the loss curve.

It also disagrees with the rest of the project on purpose. The fleet has five
CORE classes and this has four, because no vendored flag produces a flight
call. That gap used to be undocumented, discovered by reading two files side by
side; these tests are what make it a stated fact with a failure attached.
"""

import pytest

from crowgpt.calltype import CORE, MISSING_FROM_CORE, _corpus, check_vocabulary


class TestTheVocabularyMatchesItsCorpus:
    def test_core_is_exactly_what_the_flags_can_produce(self):
        assert set(CORE) == set(_corpus().FLAG_TO_CORE.values())

    def test_and_the_check_passes_as_shipped(self):
        check_vocabulary()

    def test_the_order_is_pinned_because_it_is_a_token_id(self):
        # Alphabetical today, and that is not the point — the point is that it
        # is written down. A checkpoint trained with `begging` at index 1 is
        # wrong the moment something re-sorts this.
        assert CORE == ("alarm call", "begging", "call", "song")


class TestTheGapToTheFleetIsNamed:
    def test_the_fleet_has_one_class_this_corpus_cannot_reach(self):
        assert set(_corpus().CORE_CLASSES) - set(CORE) == set(MISSING_FROM_CORE)

    def test_and_it_is_flight_call(self):
        # The class with the best AUC in the project is the one the generator
        # cannot be asked for. Worth failing loudly if that ever changes, in
        # either direction — see FUTURE.txt on merging crowgpt with a
        # crow-to-human model, which turns on this list.
        assert MISSING_FROM_CORE == ("flight call",)

    def test_this_vocabulary_is_a_subset_of_the_fleet_s(self):
        # A class here that the fleet does not know would be worse than the
        # gap: the generator could produce a label nothing else can read.
        assert set(CORE) <= set(_corpus().CORE_CLASSES)


class TestDriftIsLoud:
    def test_a_new_flag_class_fails_the_check(self, monkeypatch):
        corpus = _corpus()
        monkeypatch.setitem(corpus.FLAG_TO_CORE, "swoop", "flight call")
        monkeypatch.setattr("crowgpt.calltype._corpus", lambda: corpus)
        with pytest.raises(ValueError, match="no longer matches"):
            check_vocabulary()

    def test_a_moved_fleet_class_fails_the_check(self, monkeypatch):
        corpus = _corpus()
        monkeypatch.setattr(corpus, "CORE_CLASSES",
                            corpus.CORE_CLASSES + ("gurgle",))
        monkeypatch.setattr("crowgpt.calltype._corpus", lambda: corpus)
        with pytest.raises(ValueError, match="fleet's classes moved"):
            check_vocabulary()
