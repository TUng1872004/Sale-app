## pure, no I/O. every branch here is a test in tests/test_stage.py
from app.domain.result import Err, Ok, Result
from app.core.schema.models import OPEN_STAGES, STAGE_ORDER, TERMINAL_STAGES, LossReason, Stage


def can_transition(
    deal: dict,
    to_stage: Stage,
    loss_reason: LossReason | None,
    *,
    report_present: bool = True,
) -> Result[None]:
    from_stage: Stage = deal["stage"]

    if not report_present:
        return Err("REPORT_REQUIRED", "Cần báo cáo cho mỗi lần chuyển giai đoạn.")

    if from_stage == to_stage:
        return Err("NO_OP", "Cơ hội đã ở giai đoạn này.")

    if from_stage in TERMINAL_STAGES:
        return Err("TERMINAL", "Cơ hội đã đóng, không thể thay đổi giai đoạn.")

    if to_stage == Stage.LOST:
        if loss_reason is None:
            return Err("LOSS_REASON_REQUIRED", "Cần chọn lý do khi đánh dấu Thua.")
        return Ok(None)

    if to_stage == Stage.WON:
        if loss_reason is not None:
            return Err("LOSS_REASON_ON_WIN", "Không được có lý do thua khi đánh dấu Thắng.")
        pass

    ## forward-only: to_stage must be exactly one step ahead in STAGE_ORDER
    if from_stage not in OPEN_STAGES:
        return Err("TERMINAL", "Cơ hội đã đóng, không thể thay đổi giai đoạn.")

    from_idx = STAGE_ORDER.index(from_stage)
    try:
        to_idx = STAGE_ORDER.index(to_stage)
    except ValueError:
        return Err("SKIP_STAGE", "Giai đoạn không hợp lệ.")

    if to_idx < from_idx:
        return Err("BACKWARD", "Không thể chuyển ngược giai đoạn.")
    if to_idx > from_idx + 1:
        return Err("SKIP_STAGE", "Không thể bỏ qua giai đoạn.")

    return Ok(None)
