from app.core.task.errors import BusinessError


def _raise_unimplemented(context, business_code):
    """终止尚未实现的 ZIM 业务，避免任务被标记为成功。"""
    raise BusinessError(f"ZIM {business_code} 业务暂未实现：{context.queue_name}")


def fl_zim_si(context):
    """FL_ZIM_SI 队列入口。"""
    _raise_unimplemented(context, "SI")


def fl_zim_vgm(context):
    """FL_ZIM_VGM 队列入口。"""
    _raise_unimplemented(context, "VGM")
