import typing as t

import pytest

from llegos import research as lgo


class Increment(lgo.Message):
    ...


class Run(lgo.Message):
    rounds: int


class Stateful(lgo.Actor):
    state: int = 0

    def receive_increment(self, msg: Increment):
        self.state += 1


class Dummy(lgo.Network):

    @classmethod
    def default(cls, actor: t.Optional[Stateful] = None):
        actors = [actor or Stateful()]
        return cls(actors=actors)

    def receive_run(self, msg: Run):
        for r in range(msg.rounds):
            reply = Increment.reply_to(msg, sender=self, receiver=self.receivers()[0])
            yield reply
            msg = reply

    def get_state(self):
        return self.actors[0].state


class AnnotatedDummy(Dummy):
    # re-annotate the actors field with our Actor subclass
    actors: t.Sequence[Stateful]


@pytest.fixture
def network_run():
    network = Dummy.default()
    with network:
        init = Run(sender=lgo.Actor(), rounds=3, receiver=network)
        print(f"Initial State: {network.get_state()}")
        for msg in lgo.message_propagate(init):
            ...
    print(f"Final State: {network.get_state()}")
    return network, msg


@pytest.fixture
def annotated_network_run():
    network = AnnotatedDummy.default()  # <-- the only difference
    with network:
        init = Run(sender=lgo.Actor(), rounds=3, receiver=network)
        print(f"Initial State: {network.get_state()}")
        for msg in lgo.message_propagate(init):
            ...
    print(f"Final State: {network.get_state()}")
    return network, msg


# all actors in a network will have their types erased
def test_network_serde(network_run):
    network, _ = network_run

    new_network = type(network).model_validate(network.model_dump())

    # first warning sign, the new network's actor lost its `state` attribute
    with pytest.raises(AttributeError):
        assert hasattr(new_network, "get_state")
        # attribute error comes from inside the method call
        new_network.get_state()

    orig_actor = network.actors[0]
    new_actor = new_network.actors[0]

    # the actor's type was erased, the type is Actor but it should be Stateful
    with pytest.raises(AssertionError):
        # if types were consistent, this assertion would pass
        assert issubclass(type(new_actor), type(orig_actor)), type(new_actor)


# if we re-annotate the `actors` field with our Actor subclass, types aren't erased
def test_network_serde_annotated(annotated_network_run):
    network, _ = annotated_network_run
    new_network = type(network).model_validate(network.model_dump())

    network_state = network.get_state()
    new_state = new_network.get_state()
    assert network_state == new_state  # ok we have our state back

    orig_actor = network.actors[0]
    new_actor = new_network.actors[0]
    # suddenly, the types are consistent
    assert isinstance(new_actor, type(orig_actor)), type(new_actor)


# all messages in a given message's ancestry experience type erasure during message serde
# likely this is for the same reason as with Actors: Message subclasses generally don't
# annotate their parent types
def test_message_serde(network_run):
    _, msg = network_run
    new_msg = type(msg).model_validate(msg.model_dump())

    # main message type is the same bc we use its model_validate method
    assert isinstance(new_msg, type(msg))

    # but the parent message on the deserialized object had its type erased
    with pytest.raises(AssertionError):
        # if types were consistent, this assertion would pass
        assert issubclass(type(new_msg.parent), type(msg.parent))
