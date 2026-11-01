import pytest

from nova.campaign import Campaign


def test_survey_reveals_world_and_records_findings() -> None:
    campaign = Campaign()

    message = campaign.perform_action("asterion")

    assert "Jungle world" in message
    assert campaign.get_system("asterion").surveyed
    assert campaign.science == 20
    assert campaign.alloys == 55
    assert "Survey complete: Asterion" in campaign.log[-1]


def test_colony_requires_survey_and_spends_resources() -> None:
    campaign = Campaign()
    campaign.perform_action("asterion")

    message = campaign.perform_action("asterion")

    assert "Colony founded" in message
    assert campaign.get_system("asterion").population == "1.2B"
    assert campaign.alloys == 33
    assert campaign.influence == 5


def test_gateway_and_two_frontier_colonies_complete_objective() -> None:
    campaign = Campaign()
    campaign.perform_action("asterion")
    campaign.perform_action("asterion")
    campaign.perform_action("vesper")
    campaign.perform_action("vesper")
    campaign.perform_action("eidolon")
    campaign.perform_action("eidolon")

    assert campaign.gateway_studied
    assert campaign.objective_complete
    assert "Frontier secured" in campaign.objective


def test_campaign_rejects_actions_without_resources() -> None:
    campaign = Campaign()
    campaign.science = 0

    with pytest.raises(ValueError, match="Not enough science"):
        campaign.perform_action("asterion")

    with pytest.raises(KeyError, match="Unknown star system"):
        campaign.perform_action("unknown")


def test_campaign_income_advances_only_with_simulated_time() -> None:
    campaign = Campaign()
    initial_alloys = campaign.alloys
    initial_date = campaign.date_label

    campaign.advance(10)

    expected_income = 10 * (0.12 + max(0, campaign.colonies - 1) * 0.08)
    assert campaign.alloys == pytest.approx(initial_alloys + expected_income)
    assert campaign.date_label != initial_date
    with pytest.raises(ValueError, match="cannot be negative"):
        campaign.advance(-1)


def test_each_system_contains_multiple_individual_objects() -> None:
    campaign = Campaign()

    assert len(campaign.systems) >= 16
    assert all(len(system.objects) >= 8 for system in campaign.systems)
    assert all(
        len({system_object.object_id for system_object in system.objects})
        == len(system.objects)
        for system in campaign.systems
    )


def test_object_survey_and_anomaly_investigation_are_separate_actions() -> None:
    campaign = Campaign()

    survey_message = campaign.perform_object_action("asterion", "deep-signal")
    assert "Anomaly detected" in survey_message
    assert campaign.get_object("asterion", "deep-signal").surveyed
    assert not campaign.get_object("asterion", "deep-signal").anomaly_resolved

    investigation_message = campaign.perform_object_action(
        "asterion",
        "deep-signal",
    )
    assert "Anomaly resolved" in investigation_message
    assert campaign.get_object("asterion", "deep-signal").anomaly_resolved


def test_habitable_object_can_be_colonized_independently() -> None:
    campaign = Campaign()
    target = campaign.get_object("asterion", "frontier")
    target.surveyed = True
    campaign.get_system("asterion").surveyed = True

    message = campaign.perform_object_action("asterion", "frontier")

    assert "Colony founded" in message
    assert target.colonized
    assert campaign.get_system("asterion").colonized
