## deactivation guard. this is the brief's required error-case demo.
from app.domain.result import Err, Ok, Result
from app.core.schema.models import SaleStatus


def can_deactivate(sale_status: SaleStatus, owned_agency_count: int, open_oppo_count: int = 0) -> Result[None]:
    if sale_status == SaleStatus.INACTIVE:
        return Err("ALREADY_INACTIVE", "Sale này đã ngừng hoạt động.")
    if owned_agency_count > 0 or open_oppo_count > 0:
        return Err(
            "REASSIGN_REQUIRED",
            f"Sale đang phụ trách {owned_agency_count} đại lý và {open_oppo_count} cơ hội mở. Cần chuyển giao trước khi ngừng hoạt động.",
        )
    return Ok(None)
