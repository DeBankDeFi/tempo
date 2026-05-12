# DeBank 自定义 RPC Dev 环境测试报告 - v1.7.0-debank

## 测试环境

- 节点: `blockchain-misc-x3` (Dev 环境)
- 镜像: `294354037686.dkr.ecr.ap-northeast-1.amazonaws.com/blockchain/tempo:d6e55f6`
- 版本: `tempo v1.7.0` (merge commit `d6e55f61c`)
- 网络: Tempo Presto mainnet (chain ID 4217, 0x1079)
- 对照: 官方 RPC `https://rpc.tempo.xyz`
- 端口: 8566 (HTTP)
- 日期: 2026-05-12
- 节点同步状态: 历史区块完整（≤ 16,905,149），最新 head 同步中（chain head ~19.5M）
- T4 状态: **pre-T4**（Moderato 5/14 16:00 CEST，Presto 5/18 16:00 CEST 之前）

---

## 1. eth_multiCall

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 1.1 | 基础 balanceOf (block latest) | **PASS** | code=0, camelCase 字段, gasUsed=271432, timeCost=0.039s |
| 1.3 | 0xeeee balanceOf | **PASS** | code=0, result=0x00...00 |
| 1.4 | 0xeeee decimals | **PASS** | code=0, result=0x12 (18) |
| 1.5 | 0xeeee totalSupply | **PASS** | code=0, result=0x01。详见下方"v1.6.0 baseline 文档差异确认" |
| 1.6 | 0xeeee 未知 selector | **PASS** | code=-40001, err="method not found"。详见下方"v1.6.0 baseline 文档差异确认" |
| 1.10 | 空请求 [] | **PASS** | results=[], stats 完整 |
| 1.11 | genesis block 0x0 | **PASS** | code=0, blockNum=0 |

---

## 2. pre_traceMany

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 2.1 | 基础 balanceOf trace | **PASS** | trace 完整含 action/result/blockHash/blockNumber/transactionHash |
| 2.3 | 空交易列表 [] | **PASS** | 返回 [] |

---

## 3. trace_debankBlock

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 3.1 | genesis block (0x0) | **PASS** | block 数据完整, height=0, txs 生成 |
| 3.2 | 多 tx 区块 0x9a1eb0 (4 txs) | **PASS** | tx=4, traces=10, events=9, err_traces=0 — 与 v1.6.0 baseline 一致 |
| 3.3 | revert tx 区块 0x9a2040 | **PASS** | tx=4, error_traces=1 — revert tx 正确归类 |
| 3.4 | create tx 区块 0x99b150 | **PASS** | tx=2, create_count=1 |
| 3.5 | EIP-1559 区块 0x9e8900 | **PASS** | block_file 含 block + txs + traces |
| 3.6 | header 字段完整性 (pre-T4) | **PASS** | block keys: id/height/parent_id/base_fee_per_gas/miner/gas_limit/gas_used/timestamp/process_start_timestamp，**`consensus_context` 字段正确缺省**（pre-T4 不写入） |

---

## 4. AA tx (0x76) 字段对齐

block 0x9a1eb0 第 3 笔 tx 是 AA tx（type=0x76），eth_getBlockByNumber 报告 hash=0xb3c022e62af3。trace_debankBlock 输出对应位置 tx[2]：

| 字段 | v1.6.0 baseline 期望 | v1.7.0 实际 | 结果 |
|------|---------------------|------------|------|
| `calls` | 存在，含 call 数组 | 存在，len=1 | **PASS** |
| `chain_id` | 存在 | 存在 | **PASS** |
| `fee_token` | 存在（TIP-20 token 地址） | 存在 | **PASS** |
| `nonce_key` | 存在（U256） | 存在 | **PASS** |
| `signature` | 存在 | 存在 | **PASS** |
| `signature_type` | secp256k1 / p256 / webAuthn | secp256k1 | **PASS** |
| `to_addr` | Address::ZERO | `0x000...` | **PASS** |
| `input` | Bytes::default() | empty | **PASS** |
| `value` | U256::ZERO | 0 | **PASS** |
| 系统 tx (tx[3], from=0x0, to=0x0, gas=0) | 单独 tx, 不归类 AA | 识别正确 | **PASS** |

---

## 5. 与官方 RPC 对比

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 5.1 | eth_chainId | **PASS** | 均返回 0x1079 |
| 5.2 | 区块数据一致性 (0x9a1eb0) | **PASS** | hash/stateRoot/transactionsRoot/receiptsRoot 4/4 完全一致 |
| 5.3 | trace_transaction (block 0x9a1eb0, 4 txs) | **4/4 PASS** | 每笔 tx 的 trace JSON 经 sha256 摘要对比完全一致 |
| 5.5 | eth_getTransactionReceipt (tx[0]) | **PASS** | status=0x1, gasUsed=0x19684, blockHash 完全一致 |

---

## 6. 压力测试

| 请求数 | 方法 | 耗时 | 结果 |
|--------|------|------|------|
| 1000 | eth_multiCall (0xeeee totalSupply) | 902ms (含网络往返) | **PASS** |

---

## 7. T4 专项前置确认（关键）

**当前 dev 测试均在 pre-T4 时段（< 2026-05-14 16:00 CEST）**。验证内容：

| # | 项 | 结果 |
|---|----|------|
| 7.1 | pre-T4 blockfile 不含 `consensus_context` 字段 | **PASS**（`block_file.block` keys 不含 consensus_context） |
| 7.2 | pre-T4 区块的 trace_debankBlock 输出与 v1.6.0 baseline 结构一致 | **PASS**（块字段、tx 字段、AA tx 字段、traces/events 数量对齐） |
| 7.3 | 与官方 v1.7.0 RPC 行为一致 | **PASS**（hash/state_root/receipts 全部 byte-identical） |

**post-T4 验证待 Moderato 5/14 / Presto 5/18 之后**，需补充：
- post-T4 区块的 `eth_getBlockByNumber` 返回应包含 `consensus_context` 字段（含 epoch/view/parent_view/proposer）
- post-T4 区块的 `trace_debankBlock` blockfile 仍不应包含 `consensus_context`（由 `alloy_rpc_types_eth::Header` 隔离）
- background-tracer 消费方仍能正确解析 blockfile

---

## 8. 容器健康

- `sudo docker compose up -d tempo` 成功启动
- 启动日志无 panic / fatal error
- `eth_chainId` / `eth_blockNumber` 响应正常
- 持续接收上游 payload（latest > 19,554,000）并 follow 模式追同步

---

## 总结

- **DeBank 自定义 RPC**: eth_multiCall 7/7 PASS, pre_traceMany 2/2 PASS, trace_debankBlock 6/6 PASS
- **AA tx 字段**: 10/10 字段对齐 v1.6.0 baseline
- **与官方 v1.7.0 RPC**: chainId / 区块数据 / trace_transaction 4/4 / receipt 全部一致
- **T4 专项前置**: pre-T4 行为正确，consensus_context 不污染 blockfile
- **节点状态**: 启动正常、持续 follow 同步
- **升级结论**: **v1.7.0-debank Dev pre-T4 验证全部通过**，可推进 prod 上线流程

## 附录：v1.6.0 baseline 文档差异确认

`docs/test-report-dev.md`（v1.6.0 baseline）里有两处描述与 v1.7.0 不符，经源码 + 真实镜像两层验证，确认是 **baseline 文档笔误**，运行时行为从未变化：

### A. 0xeeee totalSupply 返回值

| 维度 | 内容 |
|------|------|
| baseline doc 描述 | `code=0, 返回 1e18` |
| v1.6.0-debank 源码 (`crates/debank-rpc/src/erc20_handle.rs`) | `result: Bytes::from(U256::from(1u32).to_be_bytes_vec())` |
| v1.6.0-debank 单测 (同文件 `mod tests`) | `assert_eq!(U256::from_be_slice(&res.result), U256::from(1u32))`，**断言返回 1** |
| **实际跑 v1.6.0-debank 镜像** | `result: "0x...0001"`（=1） |
| **实际跑 v1.7.0 d6e55f6 镜像** | `result: "0x...0001"`（=1） |
| 源码 diff `git diff v1.6.0-debank HEAD -- crates/debank-rpc/src/erc20_handle.rs` | 仅 cargo fmt 空白差异 |

### B. 0xeeee 未知 selector 错误消息

| 维度 | 内容 |
|------|------|
| baseline doc 描述 | `code=-40001, err="no method with id: 0xdeadbeef"` |
| 全仓库 grep `"no method with id"` | **0 hit**（任何 tag/branch/历史 commit 都没出现过这字符串） |
| v1.6.0-debank 源码 fallback 分支 | `err: "method not found".to_string()` |
| v1.7.0 同源码 | 完全相同 |
| **实际跑 v1.6.0-debank 镜像** | `code: -40001, err: "method not found"` |
| **实际跑 v1.7.0 d6e55f6 镜像** | `code: -40001, err: "method not found"` |

### 验证方法
1. `git diff v1.6.0-debank HEAD -- crates/debank-rpc/src/erc20_handle.rs` 看源码无逻辑变化
2. `git log --all -S 'no method with id'` 看历史从无该字符串
3. SSH dev 机切镜像 tag `v1.6.0-debank` 跑同样请求，再切回 `d6e55f6` 跑同样请求，对比响应 byte-identical

**结论**：两处都是 v1.6.0 baseline 报告写作时口语化/记忆失准导致的文档错误，跟 v1.7.0 升级无关。本次 v1.7.0 dev 验证的 1.5 / 1.6 仍判 PASS。

---

## 待 post-T4 时段补充

- [ ] Moderato 5/14 16:00 CEST 后：取一个 post-T4 moderato 区块验证 `consensus_context` 字段出现在 `eth_getBlockByNumber` 响应中
- [ ] Presto 5/18 16:00 CEST 后：在 mainnet 节点同上验证
- [ ] 跑 post-T4 区块的 trace_debankBlock 确认 blockfile 输出 schema 未变（不应 break background-tracer 消费）
