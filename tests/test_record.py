"""密钥生成仪式的严格验收测试。

初始状态下，本文件的 15 条测试必须全部失败，且失败原因只能是
NotImplementedError。不要为了让测试变绿而修改本文件。
"""

import copy

import pytest

from ceremony.record import (
    abort,
    append_event,
    ceremony_batch,
    next_step,
    open_ceremony,
    threshold_met,
    validate_record,
    witness_sign,
)


NOW = 1_000
STEPS = ["prepare", "collect", "combine", "attest"]
WITNESSES = ["alice", "bob", "carol"]


def config(**overrides):
    values = {
        "ceremony_id": "alpha",
        "steps": list(STEPS),
        "timeout": 120,
        "witnesses": list(WITNESSES),
        "threshold": 2,
    }
    values.update(overrides)
    return values


def event(event_id, step):
    return {"id": event_id, "step": step}


def opened(**overrides):
    return open_ceremony(config(**overrides), NOW)


def add(state, event_id, step, at):
    return append_event(state, event(event_id, step), at)


def sign(state, witness, event_id, at):
    return witness_sign(state, witness, event_id, at)


def test_defect_01_append_event_rejects_step_skip():
    state = opened()

    with pytest.raises(ValueError):
        add(state, "evt-1", "collect", NOW + 1)

    assert state["events"] == []
    assert next_step(state)["step"] == "prepare"


def test_defect_02_append_event_rejects_after_deadline():
    state = opened()

    with pytest.raises(ValueError):
        add(state, "evt-late", "prepare", NOW + 121)

    assert state["events"] == []

    # 被篡改的历史记录中若已有越界事件，validate_record 也必须报告。
    state["events"] = [
        {"id": "evt-late", "step": "prepare", "at": NOW + 121}
    ]
    issues = validate_record(state)
    assert any("时间" in issue for issue in issues)


def test_defect_03_witness_cannot_sign_same_event_twice():
    state = opened()
    state = add(state, "evt-1", "prepare", NOW + 1)
    state = sign(state, "alice", "evt-1", NOW + 2)

    with pytest.raises(ValueError):
        sign(state, "alice", "evt-1", NOW + 3)

    assert [item["witness"] for item in state["signatures"]] == ["alice"]


def test_defect_04_threshold_counts_unique_witnesses_only():
    state = opened()
    state = add(state, "evt-1", "prepare", NOW + 1)

    # 模拟历史记录中已经存在的重复签名：阈值只能按人计算。
    state["signatures"].extend(
        [
            {"witness": "alice", "event_id": "evt-1", "at": NOW + 2},
            {"witness": "alice", "event_id": "evt-1", "at": NOW + 3},
        ]
    )
    assert threshold_met(state, "evt-1", 2) is False
    assert any(
        ("重复" in issue) or ("多次" in issue)
        for issue in validate_record(state)
    )

    state["signatures"].append(
        {"witness": "bob", "event_id": "evt-1", "at": NOW + 4}
    )
    assert threshold_met(state, "evt-1", 2) is True


def test_defect_05_abort_stops_all_later_events():
    state = opened()
    state = add(state, "evt-1", "prepare", NOW + 1)
    state = abort(state, "witness unavailable", NOW + 2)

    assert state["status"] == "aborted"
    assert state["abort_reason"] == "witness unavailable"
    with pytest.raises(ValueError):
        add(state, "evt-2", "collect", NOW + 3)
    with pytest.raises(ValueError):
        sign(state, "alice", "evt-1", NOW + 3)
    assert [item["id"] for item in state["events"]] == ["evt-1"]
    assert next_step(state) == {}


def test_defect_06_aborted_ceremony_cannot_be_reopened():
    state = opened()
    state = abort(state, "threshold compromised", NOW + 2)

    # 把既有记录当作重新开启请求时，open 必须检查原状态并拒绝。
    with pytest.raises(ValueError):
        open_ceremony(state, NOW + 3)

    assert state["status"] == "aborted"


def test_defect_07_validate_rejects_non_roster_witness():
    state = opened()
    state["events"] = [{"id": "evt-1", "step": "prepare", "at": NOW + 1}]
    state["signatures"] = [
        {"witness": "mallory", "event_id": "evt-1", "at": NOW + 2},
        {"witness": "bob", "event_id": "evt-1", "at": NOW + 2},
    ]

    issues = validate_record(state)
    assert any("名单" in issue for issue in issues)


def test_defect_08_validate_rejects_non_monotonic_events():
    state = opened()
    state["events"] = [
        {"id": "evt-1", "step": "prepare", "at": NOW + 10},
        {"id": "evt-2", "step": "collect", "at": NOW + 5},
    ]

    issues = validate_record(state)
    assert any(
        ("时间" in issue) or ("倒序" in issue) or ("单调" in issue)
        for issue in issues
    )


def test_defect_09_validate_rejects_missing_signatures():
    state = opened()
    state["events"] = [{"id": "evt-1", "step": "prepare", "at": NOW + 1}]
    state["signatures"] = [
        {"witness": "alice", "event_id": "evt-1", "at": NOW + 2}
    ]

    issues = validate_record(state)
    assert any(("签名" in issue) or ("阈值" in issue) for issue in issues)


def test_defect_10_batch_does_not_reuse_ceremony_state():
    configs = [
        config(ceremony_id="alpha", steps=["one", "two"]),
        config(ceremony_id="beta", steps=["one", "two"]),
    ]
    batches = [
        [event("a-1", "one"), event("a-2", "two")],
        [event("b-1", "one")],
    ]

    records = ceremony_batch(batches, configs, NOW)

    assert set(records) == {"alpha", "beta"}
    assert [item["id"] for item in records["alpha"]["events"]] == [
        "a-1",
        "a-2",
    ]
    assert [item["id"] for item in records["beta"]["events"]] == ["b-1"]
    assert records["alpha"]["events"] is not records["beta"]["events"]


def test_legal_flow_completes_and_meets_threshold():
    state = opened()
    for index, step in enumerate(STEPS):
        event_id = "evt-{}".format(index)
        state = add(state, event_id, step, NOW + 1 + index * 2)
        state = sign(state, "alice", event_id, NOW + 2 + index * 2)
        state = sign(state, "bob", event_id, NOW + 2 + index * 2)

    assert next_step(state) == {}
    assert state["status"] == "completed"
    assert threshold_met(state, "evt-0", 2) is True
    assert validate_record(state) == []


def test_step_skip_is_rejected_after_progress():
    state = opened()
    state = add(state, "evt-1", "prepare", NOW + 1)

    with pytest.raises(ValueError):
        add(state, "evt-2", "combine", NOW + 2)

    assert [item["step"] for item in state["events"]] == ["prepare"]


def test_same_witness_repeated_signature_counts_once():
    state = opened()
    state = add(state, "evt-1", "prepare", NOW + 1)
    state = sign(state, "alice", "evt-1", NOW + 2)

    with pytest.raises(ValueError):
        sign(state, "alice", "evt-1", NOW + 3)

    state["signatures"].append(copy.deepcopy(state["signatures"][0]))
    assert threshold_met(state, "evt-1", 2) is False

    state = sign(state, "bob", "evt-1", NOW + 4)
    assert threshold_met(state, "evt-1", 2) is True


def test_timeout_blocks_continuation():
    state = opened()
    state = add(state, "evt-1", "prepare", NOW + 1)
    state = sign(state, "alice", "evt-1", NOW + 2)
    late = state["deadline"] + 1

    with pytest.raises(ValueError):
        add(state, "evt-2", "collect", late)
    with pytest.raises(ValueError):
        sign(state, "bob", "evt-1", late)

    assert next_step(state) == {}
    assert [item["id"] for item in state["events"]] == ["evt-1"]


def test_batch_matches_individual_runs():
    configs = [
        config(ceremony_id="alpha", steps=["one", "two"]),
        config(ceremony_id="beta", steps=["one", "two"]),
    ]
    batches = [
        [event("a-1", "one"), event("a-2", "two")],
        [event("b-1", "one")],
    ]

    records = ceremony_batch(batches, configs, NOW)

    alpha = open_ceremony(config(ceremony_id="alpha", steps=["one", "two"]), NOW)
    alpha = add(alpha, "a-1", "one", NOW + 1)
    alpha = add(alpha, "a-2", "two", NOW + 2)

    beta = open_ceremony(config(ceremony_id="beta", steps=["one", "two"]), NOW)
    beta = add(beta, "b-1", "one", NOW + 1)

    assert records["alpha"] == alpha
    assert records["beta"] == beta