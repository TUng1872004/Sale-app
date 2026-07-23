## reassignment guard + which oppo follow an agency's new owner
from app.domain.result import Err, Ok, Result
from app.core.schema.models import OPEN_STAGES, SaleStatus, Stage


def can_reassign(target_status: SaleStatus) -> Result[None]:
    if target_status != SaleStatus.ACTIVE:
        return Err("TARGET_INACTIVE", "Không thể chuyển giao cho Sale đã ngừng hoạt động.")
    return Ok(None)


def oppo_follows_reassign(stage: Stage) -> bool:
    ## closed deals stay credited to their original owner, open ones move with the agency
    return stage in OPEN_STAGES
