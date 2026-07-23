from app.core.schema.models import LossReason, Stage


STAGE_LABEL = {
    Stage.NEW: "Mới",
    Stage.QUALIFY: "Đánh giá",
    Stage.PROPOSE: "Báo giá",
    Stage.NEGOTIATE: "Đàm phán",
    Stage.WON: "Thắng",
    Stage.LOST: "Thua",
    Stage.CLOSED: "Đã đóng",
}

LOSS_LABEL = {
    LossReason.PRICE: "Giá cao",
    LossReason.COMPETITOR: "Thua đối thủ",
    LossReason.NO_DECISION: "Không ra quyết định",
    LossReason.POOR_FIT: "Không phù hợp",
    LossReason.CANCELLED: "Huỷ dự án",
    LossReason.TIMING: "Trì hoãn",
}
