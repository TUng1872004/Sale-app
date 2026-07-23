## reassignment invariants: target must be ACTIVE, open deals follow, closed deals don't
from app.domain.assign import can_reassign
from app.core.schema.models import SaleStatus, Stage


def test_can_reassign_to_active_sale():
    r = can_reassign(target_status=SaleStatus.ACTIVE)
    assert r.ok


def test_cannot_reassign_to_inactive_sale():
    r = can_reassign(target_status=SaleStatus.INACTIVE)
    assert not r.ok
    assert r.code == "TARGET_INACTIVE"


class TestOppoFollowsOwnerOnReassign:
    def test_open_oppo_follows_new_owner(self):
        from app.domain.assign import oppo_follows_reassign

        assert oppo_follows_reassign(Stage.NEW) is True
        assert oppo_follows_reassign(Stage.NEGOTIATE) is True

    def test_closed_oppo_does_not_follow(self):
        from app.domain.assign import oppo_follows_reassign

        assert oppo_follows_reassign(Stage.WON) is False
        assert oppo_follows_reassign(Stage.LOST) is False
