## every rule in plan's "Invariants the schema cannot express" -> one test each
from datetime import datetime

import pytest

from app.domain.stage import can_transition
from app.core.schema.models import LossReason, Stage


def _base_deal(stage: Stage, loss_reason: LossReason | None = None) -> dict:
    return {
        "stage": stage,
        "loss_reason": loss_reason,
        "open_at": datetime(2026, 1, 1),
    }


class TestForwardOnly:
    def test_negotiate_to_won_allowed(self):
        r = can_transition(_base_deal(Stage.NEGOTIATE), Stage.WON, None)
        assert r.ok

    def test_cannot_skip_stage(self):
        r = can_transition(_base_deal(Stage.NEW), Stage.NEGOTIATE, None)
        assert not r.ok
        assert r.code == "SKIP_STAGE"

    def test_cannot_go_backward(self):
        r = can_transition(_base_deal(Stage.PROPOSE), Stage.QUALIFY, None)
        assert not r.ok
        assert r.code == "BACKWARD"


class TestLostFromAnyOpenStage:
    @pytest.mark.parametrize("stage", [Stage.NEW, Stage.QUALIFY, Stage.PROPOSE, Stage.NEGOTIATE])
    def test_any_open_stage_can_go_lost(self, stage):
        r = can_transition(_base_deal(stage), Stage.LOST, LossReason.PRICE)
        assert r.ok


class TestTerminalImmutable:
    def test_won_cannot_transition_out(self):
        r = can_transition(_base_deal(Stage.WON), Stage.LOST, LossReason.PRICE)
        assert not r.ok
        assert r.code == "TERMINAL"

    def test_closed_cannot_transition_out(self):
        r = can_transition(_base_deal(Stage.CLOSED), Stage.NEW, None)
        assert not r.ok
        assert r.code == "TERMINAL"

class TestLossReasonRequired:
    def test_lost_without_reason_rejected(self):
        r = can_transition(_base_deal(Stage.NEGOTIATE), Stage.LOST, None)
        assert not r.ok
        assert r.code == "LOSS_REASON_REQUIRED"
