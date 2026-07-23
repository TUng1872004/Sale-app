## the brief's required error-case demo: deactivate a Sale who still owns an Agency
from app.domain.sale import can_deactivate
from app.core.schema.models import SaleStatus


def test_cannot_deactivate_sale_owning_agency():
    r = can_deactivate(sale_status=SaleStatus.ACTIVE, owned_agency_count=3)
    assert not r.ok
    assert r.code == "REASSIGN_REQUIRED"


def test_cannot_deactivate_already_inactive_sale():
    r = can_deactivate(sale_status=SaleStatus.INACTIVE, owned_agency_count=0)
    assert not r.ok
    assert r.code == "ALREADY_INACTIVE"


def test_cannot_deactivate_sale_owning_open_opportunity():
    r = can_deactivate(sale_status=SaleStatus.ACTIVE, owned_agency_count=0, open_oppo_count=1)
    assert not r.ok
    assert r.code == "REASSIGN_REQUIRED"
