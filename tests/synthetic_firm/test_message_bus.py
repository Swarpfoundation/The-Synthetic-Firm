import pytest

from synthetic_firm.message_bus import MessageRoutingError, create_message


def test_message_routes_to_channel():
    message = create_message(sender_agent_id="atlas", channel="company", content="Daily standup starts.")

    assert message.channel == "company"
    assert message.recipient_agent_id is None
    assert message.sender_agent_id == "atlas"


def test_message_requires_single_route():
    with pytest.raises(MessageRoutingError):
        create_message(
            sender_agent_id="atlas",
            recipient_agent_id="sentinel",
            channel="company",
            content="Ambiguous route",
        )
