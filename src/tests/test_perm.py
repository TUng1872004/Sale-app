## every "Cannot" row in the plan's role table -> one assertion. role system is graded evidence.
from app.domain.perm import (
    can_cross_team_reassign,
    can_reassign_in_team,
    can_view_oppo,
)
from app.core.schema.models import Role

SALER_A = {"id": "s1", "role": Role.SALER, "mgr_id": "m1"}
SALER_B = {"id": "s2", "role": Role.SALER, "mgr_id": "m1"}  # same team as SALER_A
SALER_C = {"id": "s3", "role": Role.SALER, "mgr_id": "m2"}  # different team
MANAGER_1 = {"id": "m1", "role": Role.MANAGER, "mgr_id": None}
MANAGER_2 = {"id": "m2", "role": Role.MANAGER, "mgr_id": None}
DIRECTOR = {"id": "d1", "role": Role.DIRECTOR, "mgr_id": None}


class TestSalerCannot:
    def test_saler_cannot_view_other_salers_oppo(self):
        r = can_view_oppo(actor=SALER_A, oppo_owner_id=SALER_B["id"])
        assert not r.ok
        assert r.code == "FORBIDDEN"

    def test_saler_can_view_own_oppo(self):
        r = can_view_oppo(actor=SALER_A, oppo_owner_id=SALER_A["id"])
        assert r.ok

class TestManagerCannot:
    def test_manager_cannot_touch_other_team(self):
        r = can_view_oppo(actor=MANAGER_1, oppo_owner_id=SALER_C["id"], oppo_owner_mgr_id=MANAGER_2["id"])
        assert not r.ok
        assert r.code == "FORBIDDEN"

    def test_manager_can_view_own_team(self):
        r = can_view_oppo(actor=MANAGER_1, oppo_owner_id=SALER_A["id"], oppo_owner_mgr_id=MANAGER_1["id"])
        assert r.ok

    def test_manager_can_reassign_within_team(self):
        r = can_reassign_in_team(actor=MANAGER_1, mgr_id_of_target_agency_owner=MANAGER_1["id"])
        assert r.ok

class TestDirectorCan:
    def test_director_cross_team_reassign(self):
        r = can_cross_team_reassign(actor=DIRECTOR)
        assert r.ok
