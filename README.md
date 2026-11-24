密钥生成仪式记录里，同一名见证人签了两次，阈值就被满足了：本仓库复现多人密钥生成仪式记录的实现缺陷，八个桩函数覆盖开启仪式、推进步骤、追加事件、见证签名、阈值判定、中止仪式、校验记录与批量推进，规格要求事件只能按既定步骤顺序进入且不得超出时间窗，见证签名按人去重，阈值只统计去重后的名单内见证人，中止后状态不可恢复，记录校验必须发现乱序、重复、越界与缺签名，十个规格级缺陷依次为事件不校验步骤顺序导致跳步被接受；事件不校验时间窗导致超时后仍可推进；见证签名不去重导致同一人可刷满足阈值；阈值判定用签名总条数而不是去重后的见证人数；中止后仍接受事件导致状态不可信；中止后再开启不校验原状态导致已中止的仪式可复活；校验不检查见证人是否在名单内导致外部人员签名有效；校验不检查事件时间单调导致倒序事件被接受；校验不检查缺失签名导致阈值未达也判通过；批量推进复用仪式状态导致第二个仪式沿用第一个仪式的事件。ceremony/record.py 是核心，tests/test_record.py 15个红。要修的是：按上面的顺序把 10 个缺陷逐个修掉。

# 密钥生成仪式记录 Bugfix

## 运行方式

在仓库根目录执行：

```powershell
python -m pytest tests -q
```

首次运行必须恰好是 `15 failed`，并且 15 条失败全部为 `NotImplementedError`。完成修复后目标为 `15 passed`。不要安装额外依赖，也不要联网。

## 任务元数据

| 字段 | 值 |
| --- | --- |
| 方向 | 安全 |
| 类型 | 漏洞检测与攻防 |
| 任务类型 | Bugfix |
| 运行环境 | Python 3, pytest |
| 外部依赖 | 无外部依赖 |

## 不可修改的测试

`tests/test_record.py` 是验收测试，不可修改。唯一允许修改的实现文件是 `src/ceremony/record.py`。不要通过改测试、改导入路径、复制实现到别处或绕过断言来让测试变绿。

## 目录与 pyproject 布局

```text
sec-key-ceremony/
  README.md
  pyproject.toml
  src/ceremony/__init__.py
  src/ceremony/record.py
  tests/test_record.py
```

`pyproject.toml` 只承载项目元数据和 pytest 配置，其中：

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
```

因此测试通过 `from ceremony.record import ...` 导入 `src/ceremony/record.py`。不要在仓库根目录再建一个 `ceremony` 包，也不要改导入路径。`record.py` 恰好有 8 个桩，全部直接抛出 `NotImplementedError`。

## 十个规格级缺陷

1. 事件不校验步骤顺序，跳步被接受。
2. 事件不校验时间窗，超时后仍可推进。
3. 见证签名不去重，同一人可刷满足阈值。
4. 阈值判定用签名总条数而不是去重后的见证人数。
5. 中止后仍接受事件，状态不可信。
6. 中止后再开启不校验原状态，已中止的仪式可复活。
7. 校验不检查见证人是否在名单内，外部人员签名有效。
8. 校验不检查事件时间单调，倒序事件被接受。
9. 校验不检查缺失签名，阈值未达也判通过。
10. 批量推进复用仪式状态，第二个仪式沿用第一个仪式的事件。

## 缺陷与测试映射

| 缺陷 | 验收测试 |
| --- | --- |
| 1 跳步被接受 | `test_defect_01_append_event_rejects_step_skip` |
| 2 超时后仍可推进 | `test_defect_02_append_event_rejects_after_deadline` |
| 3 同一见证人重复签名 | `test_defect_03_witness_cannot_sign_same_event_twice` |
| 4 阈值按签名总条数 | `test_defect_04_threshold_counts_unique_witnesses_only` |
| 5 中止后仍接受事件 | `test_defect_05_abort_stops_all_later_events` |
| 6 已中止仪式可复活 | `test_defect_06_aborted_ceremony_cannot_be_reopened` |
| 7 名单外见证人有效 | `test_defect_07_validate_rejects_non_roster_witness` |
| 8 倒序事件被接受 | `test_defect_08_validate_rejects_non_monotonic_events` |
| 9 缺签名也判通过 | `test_defect_09_validate_rejects_missing_signatures` |
| 10 批量复用状态 | `test_defect_10_batch_does_not_reuse_ceremony_state` |

另外 5 条测试是：

| 场景 | 验收测试 |
| --- | --- |
| 合法流程完成且阈值满足 | `test_legal_flow_completes_and_meets_threshold` |
| 跳步被拒 | `test_step_skip_is_rejected_after_progress` |
| 同一见证人重复签名只算一次 | `test_same_witness_repeated_signature_counts_once` |
| 超时后被拒 | `test_timeout_blocks_continuation` |
| 两批独立推进与单独推进相同 | `test_batch_matches_individual_runs` |

## 赛道要求的重点断言

- 同一见证人对同一事件重复签名只算一次，阈值只按去重后的见证人计数。
- 事件必须严格按 `steps` 的顺序追加，不能跳过、重复或回退步骤。
- 超过 `deadline` 后，追加事件和见证签名都必须失败，`next_step` 不再给出步骤。
- 调用 `abort` 后仪式不可继续，事件、签名和重新开启都被拒绝。

## 记录字段契约

`config` 至少包含：

| 字段 | 含义 |
| --- | --- |
| `ceremony_id` | 仪式唯一标识 |
| `steps` | 严格有序的步骤名列表 |
| `timeout` | 从开始时间起算的超时秒数 |
| `witnesses` | 允许签名的见证人名单 |
| `threshold` | 达到有效所需的去重见证人数 |

`open_ceremony` 返回的仪式记录至少包含：

| 字段 | 含义 |
| --- | --- |
| `config` | 配置快照 |
| `started_at` | 开始时间 |
| `deadline` | 截止时间，等于开始时间加 `timeout` |
| `status` | `open`、`completed`、`aborted` 或 `expired` |
| `step_index` | 下一个待执行步骤的下标 |
| `events` | 已接受的事件列表 |
| `signatures` | 已接受的签名列表 |
| `abort_reason` | 中止原因，未中止时为 `None` |
| `aborted_at` | 中止时间，未中止时为 `None` |

事件字典使用 `id`、`step`，可选的 `payload` 不参与判定；`append_event` 必须把 `at` 写成传入的 `now`。签名条目使用 `witness`、`event_id`、`at`。`next_step` 在还有步骤时返回形如 `{"index": 0, "step": "prepare"}` 的字典，在结束、中止或超时后返回 `{}`。

`append_event`、`witness_sign` 和 `abort` 原地更新并返回仪式记录；违反步骤顺序、时间窗、唯一性或状态约束时抛出 `ValueError`。若 `open_ceremony` 收到的是既有仪式记录且其 `status` 为 `aborted`，也必须抛出 `ValueError`，不能把已中止的仪式重新开启。`validate_record` 返回中文问题字符串列表，没有问题时返回 `[]`，并且必须一次性收集所有问题，不能只报第一个。

`ceremony_batch(events, config, now)` 的 `events` 是事件列表的列表，`config` 是与外层等长的配置列表；返回值以 `ceremony_id` 为键，每个仪式必须使用全新的状态、事件列表和签名列表，不能共享可变对象。

## 完成标准

15 条测试全部通过，且实现只改 `src/ceremony/record.py`。建议按缺陷编号顺序修复，每修一个就运行一次 `python -m pytest tests -q`，确保没有回归。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 安全 |
| 子方向 | 漏洞检测与攻防 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

