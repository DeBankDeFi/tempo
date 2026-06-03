# DeBank tempo v1.8.0 — 测试计划

## 上下文

v1.8.0 是 upstream tempo v1.8.0 合入 debank fork（PR #10，merge commit `41801ffdc`），吸收 251 个 upstream commit。**依赖大升级、debank-rpc 零源码改动**：

- revm-inspectors 0.36 → **0.40.0**
- revm → **40.0.3**（context-interface 17 → 19）
- reth → rev **aec6ba0**
- alloy 2.0.4 → **2.0.5**

已完成的初步验证（不替代本计划）：
- 本地 `cargo check --workspace` 0/0、`clippy -p debank-rpc -D warnings` clean、`cargo test -p debank-rpc` 20 passed
- dev sanity：`trace_debankBlock` 5 块 byte-identical vs v1.7.0（排除运行时 `process_start_timestamp`）

本计划是 **release `v1.8.0-debank` 前的系统化回归**，在 v1.7.0 的 `docs/test-report-v1.7.0-full-regression.md`（13 section × 11 块 = 2029 断言 + 60 块 dev-vs-official）基础上，新增两块覆盖：

1. **post-T4 专项**——T4 已于 mainnet 激活（当前 head timestamp `1780457880` > T4 `1779112800`），v1.7.0 测试时 T4 未激活、`consensus_context` 字段无法实测，本次补上。
2. **完整 pipeline 一致性**——dev 现部署完整通用架构（writer + etl + leafage + consistency），新增 leafage-vs-writer 与 consistency 端到端验证。

## 测试目标

| 目标 | 判定 |
|---|---|
| G1 v1.8.0 升级无回归 | debank RPC 输出与 v1.7.0 byte-identical（重点：reth/revm/inspectors 大升级不影响 trace/multiCall/pre 输出） |
| G2 post-T4 正确 | post-T4 块 `consensus_context` 出现、blockfile schema 不变、trace 分类正确 |
| G3 与官方 RPC 一致 | writer 标准 RPC（block/receipt/trace_transaction）byte-identical vs `rpc.tempo.xyz` |
| G4 完整 pipeline 一致 | leafage RPC == writer；consistency-checker 无 mismatch |
| G5 节点健康 | 同步 live、无 panic、压测后稳定 |

## 测试环境

- **节点**：`lihe-dev`（172.21.52.10），`/data/tempo-t4/` 完整通用架构
- **被测镜像**：`294354037686.dkr.ecr.ap-northeast-1.amazonaws.com/blockchain/tempo:41801ff`（v1.8.0）
- **对照源**：
  - dev 自身标准 RPC（`eth_getBlockByNumber` / `eth_getTransactionReceipt` / `trace_transaction`）
  - 官方 `https://rpc.tempo.xyz`（需带 `User-Agent` header，否则 403）
  - leafage RPC（`http://127.0.0.1:8536`）做 pipeline 侧对照
- **链**：Tempo Presto mainnet（chain id 4217），head ≈ 23,324,xxx（post-T4，T5 未激活，约 6/5）
- **脚本**：`scripts/full_regression.py`、`scripts/dev_vs_official.py`（已在仓库）

### 前置：把 dev writer 切到 v1.8.0

当前 dev writer 是 x1 迁来的 v1.7.0（`d6e55f6`）。测 v1.8.0 前需切镜像（reth db 兼容，已验证 v1.7.0→v1.8.0 正常打开）：

```bash
ssh lihe-dev
cd /data/tempo-t4
# 改 writer image d6e55f6 -> 41801ff
sudo sed -i 's#blockchain/tempo:d6e55f6#blockchain/tempo:41801ff#' docker-compose.yml
sudo docker compose up -d writer
# 等 live sync（warm 原卷，秒级追上），确认 eth_syncing=false
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"eth_syncing","params":[],"id":1}' http://127.0.0.1:8566
```

> 启动会有 WARN `Storage settings mismatch storage_v2 stored=false requested=true`——v1.8.0 新引入 storage_v2，旧 db 沿用 v1，不影响功能，符合预期。

## 测试块矩阵（13 块：v1.7.0 的 11 块 + 2 个 post-T4 新增）

| ID | Block | T 状态 | 特征 |
|----|-------|--------|------|
| B1 | 0 | genesis | 15 synthetic txs（chain spec 构造） |
| B2 | 1 | early | 空块（仅系统 tx） |
| B3 | 10,100,400 | pre-T3 | 主测试块，含 AA tx (secp256k1) |
| B4 | 10,100,800 | pre-T3 | revert tx，revert 前无 EVM event |
| B5 | 10,084,700 | pre-T3 | revert tx + 6 EVM event before revert |
| B6 | 10,072,400 | pre-T3 | CREATE trace |
| B7 | 10,389,760 | pre-T3 | EIP-1559 tx |
| B8 | 17,074,116 | post-T3 | address_registry (TIP-1022) + AA secp256k1 |
| B9 | 18,505,730 | post-T3 | address_registry + AA webAuthn |
| B10 | 18,210,816 | post-T3 | AA tx |
| B11 | 19,600,000 | post-T3 | 高 tx 数 (5 Legacy) |
| **B12** | **~22,000,000** | **post-T4** | **首个含 `consensus_context` 的测试块（选 timestamp > 1779112800 的块）** |
| **B13** | **head − 100** | **post-T4 near-head** | **近 head 块，含 consensus_context + 最新 tx 类型分布** |

> B12/B13 的具体块号在执行时用 `eth_getBlockByNumber` 按 timestamp > 1779112800 选定；优先选含 AA tx + 非空 trace 的块。

## 一、trace_debankBlock 13-section 回归（沿用 v1.7.0）

对 13 块跑 `scripts/full_regression.py`，逐字段断言。13 个 section：

| Section | 名称 | 关键断言 |
|---|---|---|
| 1 | 顶层结构 | block_file / header / state_diff / validation_hash 4 字段 |
| 2 | block fields | id/height/parent_id/miner/gas_limit/gas_used/timestamp 等 9 字段 |
| 3 | txs 字段 + 类型覆盖 | 每种 tx type (0x0/0x2/0x76 AA) 字段完整 |
| 4 | traces | 11 字段 + 类型 ⊆ {call,create,suicide} + id 全局唯一 + count == Σ trace_transaction |
| 5 | events | 8 字段 + idx 唯一+连续 + 计数公式 `events + revert_receipt_logs == total_receipt_logs` |
| 6 | error_traces/error_events | revert 分类正确、全成功块无 error、root error 字段非空 |
| 7 | storage_contracts | 类型 + 空块约束 |
| 8 | state_diff | RLP decode + `state_diff.hash == header.stateRoot` |
| 9 | header 20 字段 | 逐字段精确匹配 `eth_getBlockByNumber` |
| 10 | validation_hash | 类型 + 非零 + 两次调用幂等 |
| 11 | 特殊块 | genesis / empty / AA 分类 / CREATE / 不存在 / latest |
| 12 | 兼容/性能 | parent_id 链 + 响应延迟 |
| 13 | 批量回归 20 块 | tx count / hash / event idx |

**通过标准**：全部断言 PASS，0 FAIL（background-tracer binary 项 N/A，与 v1.7.0 一致）。

```bash
scp scripts/full_regression.py lihe-dev:/tmp/
# full_regression.py 里 RPC 端口确认为 8566；测试块加入 B12/B13
ssh lihe-dev 'python3 /tmp/full_regression.py'
```

## 二、post-T4 专项（v1.8.0 新增，对应 G2）

T4 已激活，补 v1.7.0 留下的待续项：

| # | 测试项 | 验证点 |
|---|--------|--------|
| 2.1 | post-T4 块 header 含 consensus_context | `eth_getBlockByNumber` 返回的 header 出现 `consensus_context`（epoch/view/parent_view/proposer） |
| 2.2 | trace_debankBlock 的 blockfile **不被 consensus_context 污染** | blockfile 的 `debank_header` 仍是 `alloy_rpc_types_eth::Header` 格式，无 consensus_context（设计：消费方不需要共识元数据） |
| 2.3 | post-T4 块 trace/event 分类正确 | B12/B13 跑完整 13 section，0 FAIL |
| 2.4 | post-T4 AA tx | post-T4 块的 AA tx (0x76) 各字段完整、分类按 receipt.status 修正 |
| 2.5 | T4 gas 行为（shared gas=0 post-T4） | trace 的 gasUsed 与 receipt 一致（v1.8.0 含 "set shared gas to 0 post-T4" #3854） |

## 三、eth_multiCall（node-rpc-testing 方法论）

按 skill 的 §一执行，重点项：

| 组 | 覆盖 |
|---|---|
| 基础功能 | balanceOf / 批量 / 0xeeee balanceOf,decimals,name,symbol,totalSupply / 0xeeee 未知 selector (-40001) |
| 参数 | fast_fail / 历史 blockNumber+blockHash / 不存在块 (-32001) / useParallel / disableCache / state_overrides / block_overrides |
| 错误码 | 0 / -40001 / -40013(Halt) / -40014(Revert) / -40015(FastFailed) |
| 字段类型 | SingleCallResult + MultiCallStats 全字段 |
| 边界 | 空请求 / block 0,1 / 早期块合约未部署 (-40014) / revert reason / 混合成功失败 |
| **v1.8.0 重点** | **与 v1.7.0 对同一组请求逐项对比**（除运行时 `timeCost`），确认 revm 40 升级未改变执行结果 |

## 四、pre_traceMany（node-rpc-testing 方法论）

按 skill 的 §二执行，重点项：

| 组 | 覆盖 |
|---|---|
| 基础 | balanceOf trace / transfer trace (含 Transfer event) / 多笔顺序 state 累积 / revert (code=1002) / gas 不足 (1000/1001) |
| 参数 | 历史 block_id / 空列表 / state_overrides / block_overrides / from-nonce-gasPrice 可选 |
| 字段 | PreResult (trace/logs/error/gasUsed) + Parity Trace 全字段 |
| 状态可见性 | revert 回滚不影响后续 / 成功→revert→查询 |
| **v1.8.0 重点** | **`transactionHash` 是 `B256::random()`（pre.rs:140），两边必然不同——对比时排除**；对比 trace/logs/gasUsed 与 v1.7.0 一致 |

## 五、writer vs 官方 RPC byte-identical（对应 G3）

跑 `scripts/dev_vs_official.py`，扩展到含 post-T4 区段：

| 区段 | 数量 | 范围 |
|------|------|------|
| pre-T3 | 30 | 10,080,000..10,100,300 |
| post-T3 | 20 | 17,100,000..19,740,000 |
| **post-T4** | **15** | **20,000,000..23,300,000（新增）** |
| near-head | 5 | head−25,000..head |

每块对比：4 个 root hash（hash/stateRoot/transactionsRoot/receiptsRoot）+ 每 tx receipt 7 字段 + 每 tx `trace_transaction` sha256 摘要。**通过标准：全块 byte-identical，0 fail**。

```bash
scp scripts/dev_vs_official.py lihe-dev:/tmp/
# 脚本内加 post-T4 区段；RPC 端口 8566
ssh lihe-dev 'python3 /tmp/dev_vs_official.py'
```

## 六、完整 pipeline 一致性（v1.8.0 新增，对应 G4）

dev 现有完整通用架构（writer → etl → kafka/S3 → leafage + consistency），验证 v1.8.0 writer 的输出经 pipeline 被下游正确消费：

| # | 测试项 | 方法 | 验证点 |
|---|--------|------|--------|
| 6.1 | leafage 追平 writer | 对比 8536 与 8566 的 `eth_blockNumber` | lag < 100 持续稳定 |
| 6.2 | leafage vs writer 标准 RPC byte-identical | 同一批块（含 post-T4）对比 `eth_getBlockByNumber` / `eth_getTransactionReceipt` / `eth_call` | 完全一致 |
| 6.3 | consistency-checker 无 mismatch | `sudo docker logs tempo-t4-consistency` + `:8886` 状态 | 无 mismatch 告警，ReplicaLatestBlockNumber 持续推进 |
| 6.4 | etl 推送连续性 | `sudo docker logs tempo-t4-etl` | offset 单调递增、无 gap、无 panic |
| 6.5 | leafage 消费 v1.8.0 输出 | 升级 writer 到 v1.8.0 后观察 leafage 是否无缝继续 | leafage 不报 decode/格式错误（v1.8.0 输出与 v1.7.0 byte-identical，应无缝） |
| 6.6 | 24h burn-in | consistency 跑 24h | 0 mismatch |

## 七、压力测试（对应 G5）

| # | 测试项 | 方法 |
|---|--------|------|
| 7.1 | eth_multiCall 批量 | 100/500/1000/5000 笔 call |
| 7.2 | pre_traceMany 批量 | 100/500/5000 笔 tx |
| 7.3 | trace_debankBlock 高 tx 块 | near-head 高 tx 数块连续调用 |
| 7.4 | 并发 | 10 并发 × 100 笔/请求 |
| 7.5 | 压测后检查 | `docker logs` 无 panic/error，4 个容器正常运行，leafage 未掉队 |

## 八、v1.8.0 升级专项回归（对应 G1，本次核心）

v1.8.0 的风险集中在依赖大升级是否改变了 debank-rpc 的输出。专项确认：

| # | 关注点 | 验证 |
|---|--------|------|
| 8.1 | revm-inspectors 0.36→0.40 | trace 树结构（subtraces/traceAddress/callType）、CallTraceNode 字段映射不变 → §一 Section 4 全过 + §五 trace_transaction byte-identical |
| 8.2 | revm 40 execution/gas | `gas.tx_gas_used()`、ExecutionResult 解构不变 → multiCall/pre 的 gasUsed 与 v1.7.0 一致 |
| 8.3 | reth aec6ba0 RPC trait | trace_transaction / eth_call / receipt 输出不变 → §五 byte-identical |
| 8.4 | alloy 2.0.5 | LocalizedTransactionTrace 序列化不变 → trace JSON 字段一致 |
| 8.5 | **v1.8.0 vs v1.7.0 直接对照** | 同一组块/请求，41801ff 输出 == d6e55f6 输出（排除运行时 `process_start_timestamp` / `timeCost` / pre 的 random `transactionHash`） |

> 8.5 可复用已验证的 5 块 byte-identical 结果并扩展到 13 块矩阵 + multiCall/pre。

## 执行顺序

1. 前置：dev writer 切 41801ff，等 live sync
2. §一 full_regression.py（13 块）→ §二 post-T4 专项
3. §三 multiCall、§四 pre_traceMany
4. §五 dev_vs_official.py（含 post-T4 区段）
5. §六 pipeline 一致性（leafage/consistency/etl）
6. §八 v1.8.0 vs v1.7.0 对照
7. §七 压测（最后跑，避免干扰前面对比）

## 报告模板

产出 `docs/test-report-v1.8.0-full-regression.md`，沿用 v1.7.0 报告结构：
- 测试环境（镜像 41801ff、head、对照源、日期）
- §一~§八 分章节 PASS/FAIL/N-A 计数
- 关键设计行为再确认（AA 分类 / revert with events / CREATE / **post-T4 consensus_context** / validation_hash 幂等）
- v1.8.0 升级专项结论（大升级零回归）
- pipeline 一致性结论
- 暂未覆盖（T5）+ 待续

## 待续（不阻塞 v1.8.0 release）

- [ ] **T5 激活后**（约 6/5，timestamp 1781013600）：跑 post-T5 块，确认 TIP-1026（logoURI / createToken overload T5+）等 T5 逻辑、blockfile schema 不变
- [ ] selfdestruct trace：Tempo 链上若出现样本再补
- [ ] signature_verifier (TIP-1020) 若出现 event 类样本再补

## 结论判定

全部 PASS 即满足 v1.8.0 release 门槛：
- §一 13 块 13 section 0 FAIL
- §二 post-T4 consensus_context 行为符合设计
- §五 dev vs official 全块 byte-identical
- §六 pipeline 三方一致、consistency 0 mismatch
- §八 v1.8.0 输出 == v1.7.0（排除运行时字段）

满足后即可 `gh release create v1.8.0-debank --repo DeBankDeFi/tempo --target debank`。
