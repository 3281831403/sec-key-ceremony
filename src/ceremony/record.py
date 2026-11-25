"""密钥生成仪式记录的唯一实现文件。

覆盖开启仪式、推进步骤、追加事件、见证签名、阈值判定、中止仪式、
校验记录与批量推进八个入口。所有状态变更都是原地更新并返回同一份记录。
"""

import copy


def _is_record(value) -> bool:
    """判断传入对象是否是一份既有的仪式记录而非配置。"""
    return isinstance(value, dict) and "status" in value and "events" in value


def open_ceremony(config, now) -> dict:
    """开启一场仪式，记录开始时间与截止时间。

    若传入的是既有仪式记录，则视为重新开启请求：已中止（以及任何已结束）
    的仪式都不能复活，必须抛出 ValueError。
    """
    if _is_record(config):
        status = config.get("status")
        if status == "aborted":
            raise ValueError("仪式已中止，不能重新开启")
        raise ValueError("仪式记录已存在（status={}），不能重新开启".format(status))

    snapshot = copy.deepcopy(config)
    timeout = snapshot.get("timeout", 0)
    return {
        "config": snapshot,
        "started_at": now,
        "deadline": now + timeout,
        "status": "open",
        "step_index": 0,
        "events": [],
        "signatures": [],
        "abort_reason": None,
        "aborted_at": None,
    }


def next_step(ceremony) -> dict:
    """返回下一项待执行步骤；已结束、已中止或已超时返回空字典。"""
    if ceremony.get("status") != "open":
        return {}
    steps = (ceremony.get("config") or {}).get("steps") or []
    index = ceremony.get("step_index", 0)
    if index >= len(steps):
        return {}
    return {"index": index, "step": steps[index]}


def _ensure_accepting(ceremony) -> None:
    """确认仪式仍处于可接受事件/签名的状态。

    已完成的仪式不再接受新事件（步骤已耗尽），但在截止时间前仍接受
    对既有事件的签名，因此这里只拦截中止与超时。
    """
    status = ceremony.get("status")
    if status == "aborted":
        raise ValueError("仪式已中止，不能再接受事件或签名")
    if status == "expired":
        raise ValueError("仪式已超时，不能再接受事件或签名")


def _check_deadline(ceremony, now) -> None:
    """超过截止时间时把仪式标记为 expired 并拒绝继续。"""
    deadline = ceremony.get("deadline")
    if deadline is not None and now > deadline:
        ceremony["status"] = "expired"
        raise ValueError("当前时间 {} 已超过截止时间 {}".format(now, deadline))


def append_event(ceremony, event, now) -> dict:
    """追加事件，并校验步骤顺序、事件编号与时间窗。"""
    _ensure_accepting(ceremony)
    _check_deadline(ceremony, now)

    if "id" not in event or "step" not in event:
        raise ValueError("事件必须包含 id 与 step")

    steps = (ceremony.get("config") or {}).get("steps") or []
    index = ceremony.get("step_index", 0)
    if index >= len(steps):
        raise ValueError("仪式步骤已全部执行完毕，不能再追加事件")

    expected = steps[index]
    if event["step"] != expected:
        raise ValueError(
            "步骤顺序错误：期望步骤 {}，实际收到 {}".format(expected, event["step"])
        )

    events = ceremony.setdefault("events", [])
    if any(item.get("id") == event["id"] for item in events):
        raise ValueError("事件编号 {} 重复".format(event["id"]))

    entry = {"id": event["id"], "step": event["step"], "at": now}
    if "payload" in event:
        entry["payload"] = copy.deepcopy(event["payload"])
    events.append(entry)

    ceremony["step_index"] = index + 1
    if ceremony["step_index"] >= len(steps):
        ceremony["status"] = "completed"
    return ceremony


def witness_sign(ceremony, witness, event_id, now) -> dict:
    """见证人对指定事件签名，同一见证人同一事件只能签一次。"""
    _ensure_accepting(ceremony)
    _check_deadline(ceremony, now)

    events = ceremony.get("events") or []
    if not any(item.get("id") == event_id for item in events):
        raise ValueError("事件 {} 不存在，不能签名".format(event_id))

    roster = (ceremony.get("config") or {}).get("witnesses") or []
    if witness not in roster:
        raise ValueError("见证人 {} 不在名单内".format(witness))

    signatures = ceremony.setdefault("signatures", [])
    for item in signatures:
        if item.get("witness") == witness and item.get("event_id") == event_id:
            raise ValueError(
                "见证人 {} 已对事件 {} 签名，不能重复签名".format(witness, event_id)
            )

    signatures.append({"witness": witness, "event_id": event_id, "at": now})
    return ceremony


def threshold_met(ceremony, event_id, threshold) -> bool:
    """判断事件是否达到阈值，只统计去重后的名单内见证人。"""
    roster = set((ceremony.get("config") or {}).get("witnesses") or [])
    unique_witnesses = {
        item.get("witness")
        for item in ceremony.get("signatures") or []
        if item.get("event_id") == event_id and item.get("witness") in roster
    }
    return len(unique_witnesses) >= threshold


def abort(ceremony, reason, now) -> dict:
    """中止仪式，此后任何事件与签名都不再被接受。"""
    if ceremony.get("status") == "aborted":
        raise ValueError("仪式已经中止，不能再重复中止")
    ceremony["status"] = "aborted"
    ceremony["abort_reason"] = reason
    ceremony["aborted_at"] = now
    return ceremony


def validate_record(ceremony) -> list[str]:
    """返回记录中的全部问题；没有问题时返回空列表。"""
    issues = []

    config = ceremony.get("config") or {}
    steps = list(config.get("steps") or [])
    roster = set(config.get("witnesses") or [])
    threshold = config.get("threshold", 0)
    deadline = ceremony.get("deadline")
    started_at = ceremony.get("started_at")
    events = list(ceremony.get("events") or [])
    signatures = list(ceremony.get("signatures") or [])

    # 事件：步骤顺序、编号唯一性、时间窗与时间单调。
    event_ids = set()
    previous_at = None
    for index, item in enumerate(events):
        event_id = item.get("id")
        step = item.get("step")
        at = item.get("at")

        if index < len(steps):
            if step != steps[index]:
                issues.append(
                    "事件 {} 的步骤顺序错误：期望 {}，实际 {}".format(
                        event_id, steps[index], step
                    )
                )
        else:
            issues.append("事件 {} 超出既定步骤数量".format(event_id))

        if event_id in event_ids:
            issues.append("事件编号 {} 重复".format(event_id))
        event_ids.add(event_id)

        if not isinstance(at, (int, float)) or isinstance(at, bool):
            issues.append("事件 {} 的时间无效".format(event_id))
            continue
        if deadline is not None and at > deadline:
            issues.append(
                "事件 {} 的时间超出时间窗：{} 晚于截止时间 {}".format(
                    event_id, at, deadline
                )
            )
        if started_at is not None and at < started_at:
            issues.append(
                "事件 {} 的时间早于仪式开始时间 {}".format(event_id, started_at)
            )
        if previous_at is not None and at < previous_at:
            issues.append(
                "事件时间倒序：事件 {} 的时间 {} 早于前一事件的时间 {}".format(
                    event_id, at, previous_at
                )
            )
        previous_at = at

    # 签名：名单校验、事件引用、时间窗与重复签名。
    repeat_counts = {}
    for item in signatures:
        witness = item.get("witness")
        event_id = item.get("event_id")
        at = item.get("at")

        if witness not in roster:
            issues.append("签名见证人 {} 不在名单内".format(witness))
        if event_id not in event_ids:
            issues.append("签名引用了不存在的事件 {}".format(event_id))
        if (
            isinstance(at, (int, float))
            and not isinstance(at, bool)
            and deadline is not None
            and at > deadline
        ):
            issues.append(
                "签名见证人 {} 的时间超出时间窗".format(witness)
            )

        key = (witness, event_id)
        repeat_counts[key] = repeat_counts.get(key, 0) + 1

    for (witness, event_id), count in repeat_counts.items():
        if count > 1:
            issues.append(
                "见证人 {} 对事件 {} 重复签名 {} 次".format(
                    witness, event_id, count
                )
            )

    # 事件是否达到去重后的名单内见证人阈值。
    for event_id in event_ids:
        valid_witnesses = {
            item.get("witness")
            for item in signatures
            if item.get("event_id") == event_id
            and item.get("witness") in roster
        }
        if len(valid_witnesses) < threshold:
            issues.append(
                "事件 {} 签名不足：去重见证人 {} 少于阈值 {}".format(
                    event_id, len(valid_witnesses), threshold
                )
            )

    return issues


def ceremony_batch(events, config, now) -> dict:
    """批量推进多场仪式，每场仪式的状态必须彼此独立。"""
    if len(events) != len(config):
        raise ValueError("事件批次与配置数量不一致")

    records = {}
    for batch_index, (batch_events, batch_config) in enumerate(zip(events, config)):
        record = open_ceremony(batch_config, now)
        for event_index, event in enumerate(batch_events):
            append_event(record, event, now + event_index + 1)
        ceremony_id = (batch_config or {}).get("ceremony_id")
        records[ceremony_id] = record
    return records
