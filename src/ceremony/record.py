"""密钥生成仪式记录的唯一实现文件。

本文件恰好包含八个桩。所有桩当前都必须直接抛出 NotImplementedError，
由做题者按照 README 中的缺陷顺序逐个补齐实现。
"""


def open_ceremony(config, now) -> dict:
    """开启一场仪式，记录开始时间与截止时间。"""
    raise NotImplementedError


def next_step(ceremony) -> dict:
    """返回下一项待执行步骤；已结束、已中止或已超时返回空字典。"""
    raise NotImplementedError


def append_event(ceremony, event, now) -> dict:
    """追加事件，并校验步骤顺序、事件编号与时间窗。"""
    raise NotImplementedError


def witness_sign(ceremony, witness, event_id, now) -> dict:
    """见证人对指定事件签名，同一见证人同一事件只能签一次。"""
    raise NotImplementedError


def threshold_met(ceremony, event_id, threshold) -> bool:
    """判断事件是否达到阈值，只统计去重后的名单内见证人。"""
    raise NotImplementedError


def abort(ceremony, reason, now) -> dict:
    """中止仪式，此后任何事件与签名都不再被接受。"""
    raise NotImplementedError


def validate_record(ceremony) -> list[str]:
    """返回记录中的全部问题；没有问题时返回空列表。"""
    raise NotImplementedError


def ceremony_batch(events, config, now) -> dict:
    """批量推进多场仪式，每场仪式的状态必须彼此独立。"""
    raise NotImplementedError