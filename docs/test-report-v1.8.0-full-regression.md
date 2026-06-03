# DeBank tempo v1.8.0 — 完整回归测试报告

## 上下文

按 `docs/test-plan-v1.8.0.md` 执行。v1.8.0（`41801ff`，PR #10）= upstream tempo v1.8.0 + debank **零源码改动**，依赖大升级（revm-inspectors 0.36→0.40 / revm→40.0.3 / reth→aec6ba0 / alloy→2.0.5）。本次在 lihe-dev 完整通用节点架构上系统回归，重点验证**升级零回归** + **post-T4 新覆盖** + **完整 pipeline 一致性**。

## 测试环境

- **节点**：`lihe-dev`（172.21.52.10），`/data/tempo-t4/` 完整通用架构（writer + etl + leafage + consistency）
- **被测镜像**：`294354037686.dkr.ecr.ap-northeast-1.amazonaws.com/blockchain/tempo:41801ff`（v1.8.0，`Starting Tempo version="1.8.0"`，eth_syncing=false）
- **对照源**：dev 自身标准 RPC（8566）+ 官方 `rpc.tempo.xyz` + leafage RPC（8536）
- **链**：Tempo Presto mainnet（chain id 4217），head ≈ 23,326,xxx（**post-T4**，T5 未激活 ~6/10）
- **脚本**：`scripts/full_regression.py`（加 B12/B13）、`scripts/dev_vs_official.py`（加 post-T4 区段）
- **日期**：2026-06-03

## 测试块矩阵（13 块）

B1–B11 沿用 v1.7.0（genesis/empty/pre-T3/post-T3/revert/create/AA/webAuthn/EIP-1559/高 tx），新增：
- **B12** = 22,500,000（`0x15752a0`）post-T4 + AA tx (0x76) + consensus_context
- **B13** = 23,300,000（`0x16387a0`）post-T4 near-head + AA tx

## 测试结果汇总

| § | 测试项 | 结果 |
|---|--------|------|
| **一** | trace_debankBlock 13 块 × 13 section | **2246 PASS / 0 FAIL / 2 N/A** |
| **二** | post-T4 consensus_context 专项 | **PASS**（标准 header 有 cc，blockfile 不含 cc，符合设计） |
| **三+四** | eth_multiCall + pre_traceMany（`multicall_pre_test.py`） | **37 PASS / 0 FAIL**（真实 TIP-20 USDC.e + 0xeeee native + 错误码 -40001/-40014/-40015 + 参数全 + 边界 + pre revert/gas不足/多笔/字段） |
| **五** | writer vs 官方 byte-identical（70 块） | **1057 PASS / 0 FAIL** |
| **六** | 完整 pipeline 一致性 | **PASS**（leafage lag=0 + 一致 + etl 0 panic；consistency 多副本受单节点限制） |
| **七** | 压力测试 | **PASS**（multiCall 5000 笔全 ok，容器健康，0 panic） |
| **八** | v1.8.0 vs v1.7.0 升级对照 | **PASS**（trace_debankBlock 5/5 byte-identical + §五 vs 官方间接证明） |

## 分项明细

### §一 trace_debankBlock 13-section 回归（2246 PASS / 0 FAIL / 2 N/A）

| Section | PASS | 说明 |
|---|---|---|
| 1 顶层结构 | 39 | 13 块 × 3 |
| 2 block fields | 117 | 13 块 × 9 字段 |
| 3 txs 字段 + 类型 | 330 | 含 0x0/0x2/0x76 AA |
| 4 traces | 869 | 全字段 + id 唯一 + count == Σ trace_transaction |
| 5 events | 501 | 8 字段 + idx 唯一连续 + 计数公式 |
| 6 error 分类 | 26 | revert 分类正确 |
| 7 storage_contracts | 14 | |
| 8 state_diff (RLP) | 26 | RLP decode + `state_diff.hash == header.stateRoot`（装 rlp 4.1.0 后） |
| 9 header 20 字段 | 260 | 13 块 × 20 字段精确匹配 |
| 10 validation_hash | 38 | 类型 + 非零 + 幂等 |
| 11 特殊块 | 7 | genesis/empty/AA/CREATE/不存在/latest |
| 12 兼容/性能 | 5（+2 N/A） | N/A: background-tracer binary 不在 dev 范围 |
| 13 批量 20 块 | 1 | tx count / hash / event idx |
| **合计** | **2246** | **0 FAIL，2 N/A** |

### §二 post-T4 consensus_context（v1.7.0 待续项，本次补上）

- **2.1** post-T4 块（0x15752a0）标准 RPC header 含 `consensusContext`：`{epoch:1041, view:14491, parentView:14490, proposer:0x45dd...}` ✓
- **2.2** 同块 `trace_debankBlock` 的 blockfile header **不含** consensus_context（设计：blockfile 用 `alloy_rpc_types_eth::Header`，消费方不需要共识元数据）✓
- **2.3** B12/B13 跑完整 13 section，0 FAIL ✓

### §三+四 eth_multiCall + pre_traceMany（37 PASS / 0 FAIL，`scripts/multicall_pre_test.py`）

> **诚实修正**：本报告初版此处仅 sanity 约 6 项（dev 自比 + 0xeeee），把 sanity 当 PASS 写了。后补全为完整 37 项自动化覆盖。

**§三 multiCall**：
- 真实 TIP-20（USDC.e `0x20c0..b9537d`，6 decimals）：decimals / symbol / totalSupply / balanceOf ✓
- 0xeeee native：decimals=18 / totalSupply=1 / balanceOf；未知 selector **-40001**；**gasUsed=0**（native 不执行真实 EVM）
- 批量 3 笔；fast_fail 第1笔 **-40014** / 第2笔 **-40015**
- 历史 blockNumber / blockHash / 不存在块 **-32001** / useParallel / disableCache
- state_overrides（注入 `0x602a..f3` → result=42）/ block_overrides / per-call from
- 错误码 -40001 / -40014（注入 revert） / 无限循环
- 字段类型（SingleCallResult + MultiCallStats 全字段）
- 边界：空请求 / block 0/1 / 混合成功失败（success=false）

**§四 pre_traceMany**：基础 call trace / TIP-20 view trace / revert(error.code=**1002**) / gas不足(**1000/1001**) / 多笔顺序 state 累积 / 历史 post-T4 block / 空列表 / PreResult + Parity trace 字段完整。`transactionHash` 为 `B256::random()`（pre.rs:140，设计）。

**测试中发现**（之前 sanity 漏掉）：
1. **0xeeee native 模拟 `gasUsed=0`**（不执行真实 EVM；真实 USDC.e decimals 调用 gasUsed=271170）——设计行为，文档应写明
2. **无限循环 + per-call gas 设过低 → 整请求 `-32000 "intrinsic gas too low"`**（Tempo intrinsic gas 高于标准 21000；skill 文档的 -40013 预期不准）
3. TIP-20 合约稀少：Tempo 多是 AA tx（to=ZERO，真实调用在 calls 数组），扫 tx.to 找不到几个合约

### §五 writer vs 官方 RPC byte-identical（1057 PASS / 0 FAIL）

70 块（30 pre-T3 + 20 post-T3 + **15 post-T4** + 5 near-head），每块对比 4 root hash + 每 tx receipt 7 字段 + 每 tx `trace_transaction` sha256。**全块 byte-identical，0 fail，58s**。这是 v1.8.0 升级零回归最强证据——reth/revm/inspectors 大升级后，标准 RPC + trace 输出与官方权威节点完全一致。

### §六 完整 pipeline 一致性

| 项 | 结果 |
|---|---|
| 6.1 leafage 追平 writer | writer=leafage=23326586，**lag=0** ✓ |
| 6.2 leafage vs writer（post-T4 块 hash+stateRoot） | **IDENTICAL** ✓ |
| 6.3 consistency-checker | 追踪 leafage + etcd 注册正常，无 mismatch；`ready_ratio 0.00<0.80`（**dev 单 leafage 副本限制**，多副本 byte-equivalent 对比需 ≥2 副本，prod 场景，非 bug） |
| 6.4 etl offset 连续 | 0 panic/error ✓ |

### §七 压力测试

- multiCall 100/500/1000/**5000** 笔批量：全部 ok（5000 笔 0.03s）
- 压测后 4 容器全 Up，writer/leafage 日志 0 panic/error

### §八 v1.8.0 vs v1.7.0 升级对照

- 前期 dev sanity：trace_debankBlock **5/5 块 byte-identical**（排除运行时 `process_start_timestamp`）
- §五 writer vs 官方 byte-identical 间接证明 revm/inspector/reth 输出对
- multiCall（除 `timeCost`）/ pre（除 random `transactionHash`）行为与 v1.7.0 一致

## 关键设计行为确认

1. **post-T4 consensus_context**：标准 header 有，blockfile 无——blockfile schema 不变，下游 pipeline 不受 T4 影响
2. **v1.8.0 升级零回归**：revm-inspectors 0.36→0.40、revm 40、reth aec6ba0、alloy 2.0.5 大升级，debank-rpc 零源码改动，输出全部对齐
3. **AA tx 分类**：B3/B8-B13 含 AA tx (0x76)，按 receipt.status 修正分类，字段完整
4. **reth db 兼容**：v1.7.0 db 被 v1.8.0 正常打开（storage_v2 mismatch WARN，旧 db 沿用 v1）

## 暂未覆盖（不阻塞 release）

| 项 | 原因 |
|---|---|
| consistency 多副本 byte-equivalent | dev 单 leafage，ready_ratio 0.00<0.80，需 ≥2 副本（prod 场景）；dev 用 §6.2 leafage-vs-writer 直接对比替代 |
| T5（约 6/10 激活） | 未激活；激活后补 post-T5 块 + TIP-1026（logoURI/createToken overload） |
| Section 12 background-tracer binary | 不在 dev 测试范围（与 v1.7.0 一致） |
| selfdestruct / signature_verifier event 样本 | 链上无样本（与 v1.7.0 一致） |

## 结论

**13 块 × 13 section = 2246 断言全 PASS（0 FAIL）+ 70 块 dev-vs-official 1057 断言全 PASS（0 FAIL）+ multiCall/pre/pipeline/压测全过。**

v1.8.0 在 reth/revm/revm-inspectors/alloy 大升级下，DeBank 自定义 RPC（trace_debankBlock / eth_multiCall / pre_traceMany）+ 标准 RPC 行为**完全对齐 v1.7.0 与官方权威节点，零回归**，并正确处理 post-T4 consensus_context。完整 pipeline（writer→etl→leafage→consistency）数据流贯通、leafage 完全追上。

**满足 v1.8.0 release 门槛**，可执行：

```bash
gh release create v1.8.0-debank --repo DeBankDeFi/tempo --target debank \
  --title "v1.8.0-debank" --notes "..."
```

## 复现

```bash
# 前置：dev writer 切 41801ff
ssh lihe-dev 'cd /data/tempo-t4 && sudo sed -i "s#tempo:d6e55f6#tempo:41801ff#" docker-compose.yml && sudo docker compose up -d writer'

# §一 + §五
scp scripts/full_regression.py scripts/dev_vs_official.py lihe-dev:/tmp/
ssh lihe-dev 'python3 -m pip install rlp --user -q; python3 /tmp/full_regression.py; python3 /tmp/dev_vs_official.py'
```
