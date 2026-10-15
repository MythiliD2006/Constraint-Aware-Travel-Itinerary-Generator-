"""Knowledge representation, ISA/inheritance, unification and resolution."""

import pytest

from app.planner.knowledge_base import get_knowledge_base
from app.planner.logic import LogicEngine, parse_query, unify


@pytest.fixture(scope="module")
def kb():
    return get_knowledge_base()


# ---- ISA relationships and property inheritance ---------------------------
def test_lineage_follows_isa_links(kb):
    assert kb.lineage("Temple") == ["Temple", "PlaceOfWorship", "HeritageSite", "Attraction"]
    assert kb.is_a("ArtGallery", "Museum")
    assert not kb.is_a("Museum", "HeritageSite")


def test_most_specific_property_wins(kb):
    birla = kb.destinations["jaipur"].attractions["birla_mandir"]
    # Instance value (40) overrides PlaceOfWorship's default (45).
    assert kb.get_property(birla, "default_duration") == (40, "birla_mandir")
    # Not on the instance or Temple -> inherited from PlaceOfWorship.
    assert kb.get_property(birla, "dress_code") == ("modest clothing expected", "PlaceOfWorship")
    assert kb.get_property(birla, "footwear_removed") == (True, "Temple")
    # Root default.
    assert kb.get_property(birla, "best_time") == ("any", "Attraction")


def test_duration_is_inherited_when_instance_omits_it(kb):
    # Every sample attraction sets a duration, so test inheritance on a copy without one.
    from dataclasses import replace
    fort = kb.destinations["jaipur"].attractions["amber_fort"]
    bare = replace(fort, own_properties={})
    assert kb.duration_of(bare) == 120          # from class Fort


def test_interests_accumulate_down_the_hierarchy(kb):
    gallery = kb.destinations["mysuru"].attractions["jaganmohan_palace"]
    assert kb.interests_of(gallery) == {"art": "ArtGallery", "history": "Museum"}
    galtaji = kb.destinations["jaipur"].attractions["galtaji"]
    assert set(kb.interests_of(galtaji)) == {"nature", "spiritual", "history"}


# ---- Unification ------------------------------------------------------------
def test_unify_binds_variables_on_both_sides():
    assert unify(("isa", "?X", "Fort"), ("isa", "Palace", "?Y")) == {"?X": "Palace", "?Y": "Fort"}


def test_unify_fails_on_constant_clash_and_arity():
    assert unify(("isa", "Fort", "?Y"), ("isa", "Palace", "?Y")) is None
    assert unify(("isa", "?X"), ("isa", "?X", "?Y")) is None
    assert unify(("isa", "?X", "?Y"), ("instance_of", "?X", "?Y")) is None


def test_unify_respects_existing_bindings():
    theta = unify(("p", "?X", "?X"), ("p", "a", "?Y"))
    assert theta is not None and theta["?Y"] == "a"
    assert unify(("p", "?X", "?X"), ("p", "a", "b")) is None


# ---- Resolution ---------------------------------------------------------------
@pytest.fixture(scope="module")
def jaipur_engine(kb):
    return LogicEngine(kb.facts_for("jaipur"))


def test_transitive_subclass(jaipur_engine):
    assert jaipur_engine.holds(("subclass_of", "Temple", "Attraction"))
    assert not jaipur_engine.holds(("subclass_of", "Attraction", "Temple"))


def test_member_of_via_isa(jaipur_engine):
    answers = jaipur_engine.ask([("member_of", "?X", "HeritageSite")])
    members = {a["bindings"]["?X"] for a in answers}
    assert {"amber_fort", "birla_mandir", "jantar_mantar"} <= members
    assert "albert_hall" not in members      # Museum is not a HeritageSite


def test_resolution_agrees_with_procedural_inheritance(kb, jaipur_engine):
    """appeals_to/2 proved by resolution must equal KnowledgeBase.interests_of."""
    for attraction in kb.destinations["jaipur"].attractions.values():
        answers = jaipur_engine.ask([("appeals_to", attraction.id, "?T")])
        assert {a["bindings"]["?T"] for a in answers} == set(kb.interests_of(attraction))


def test_conjunctive_query_and_proof_trace(jaipur_engine):
    answers = jaipur_engine.ask(parse_query("candidate(?X, spiritual, jaipur, monday)"))
    assert {a["bindings"]["?X"] for a in answers} == {"birla_mandir", "galtaji"}
    assert answers[0]["proof"][0]["goal"].startswith("candidate(")


def test_closed_day_fact_blocks_candidate(kb):
    engine = LogicEngine(kb.facts_for("mysuru"))
    assert not engine.holds(("open_on", "rail_museum", "monday"))
    assert engine.holds(("candidate", "rail_museum", "history", "mysuru", "tuesday"))
    assert not engine.holds(("candidate", "rail_museum", "history", "mysuru", "monday"))


def test_parse_query_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_query("member_of(?X HeritageSite")
    with pytest.raises(ValueError):
        parse_query("member_of(?X, Heritage Site)")
    assert parse_query("isa(Fort, ?C), isa(?C, ?D).") == [("isa", "Fort", "?C"), ("isa", "?C", "?D")]
