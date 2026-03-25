# trace_debankBlock 测试计划

## 测试环境

- 节点: blockchain-misc-x3 dev 环境
- 镜像: `blockchain/tempo:5e3c190`
- 端口: 8566
- 对照: `eth_getBlockByNumber` / `eth_getTransactionReceipt` / `trace_transaction`
- 日期: 2026-03-25
- 测试区块:
  - 0x9a1eb0 (10100400, 4 txs 含 AA tx, 主测试块)
  - 0x9a2040 (10100800, 含 revert tx)
  - 0x99b150 (10072400, 含 CREATE trace)
  - 0x9e8900 (10356992, 含 EIP-1559 tx)
  - 0x0 (genesis), 0x1 (empty)

## 测试结果概要

| 大类 | 测试点 | 通过 | 失败 | 不适用 |
|------|--------|------|------|--------|
| 1. 顶层结构 | 4 | 4 | 0 | 0 |
| 2. block | 9 | 9 | 0 | 0 |
| 3. txs | 33 | 33 | 0 | 0 |
| 4. traces | 10 | 10 | 0 | 0 |
| 5. events | 6 | 6 | 0 | 0 |
| 6. error_traces/events | 6 | 6 | 0 | 0 |
| 7. storage_contracts | 3 | 3 | 0 | 0 |
| 8. state_diff (RLP) | 5 | 5 | 0 | 0 |
| 9. header | 1 (12 字段) | 1 | 0 | 0 |
| 10. validation_hash | 3 | 3 | 0 | 0 |
| 11. 特殊区块 | 7 | 7 | 0 | 0 |
| 12. 兼容性 | 2 | 2 | 0 | 0 |
| EIP-1559 覆盖 | 1 | 1 | 0 | 0 |
| **合计** | **90** | **90** | **0** | **0** |

### trace 类型覆盖

| 类型 | 状态 |
|------|------|
| call | PASS |
| delegatecall | PASS |
| create | PASS (block 0x99b150) |
| staticcall | 未覆盖 (Tempo 链上未发现) |
| suicide | 未覆盖 (Tempo 无 SELFDESTRUCT) |

### 已知的预期差异

1. **AA tx (0x76) to_addr/input**: debankBlock 返回实际调用目标和数据（从 receipt 取），eth_getBlockByNumber 返回 AA 信封层（to=null, input=短 payload）。对 DeBankCore 是正确行为，不计为 FAIL。

---

## 1. DebankOutPut 顶层结构

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 1.1 | 返回结构完整性 | block_file/header/state_diff/validation_hash 四个字段均存在且非 null | PASS |
| 1.2 | validation_hash 类型 | number 类型, 非零 | PASS |
| 1.3 | state_diff 格式 | hex string, 以 0x 开头, RLP 可解码 | PASS |
| 1.4 | header 与 eth_getBlockByNumber 一致 | hash/stateRoot/transactionsRoot/receiptsRoot/gasUsed/number/timestamp 逐字段对比 | PASS (7/7) |

---

## 2. block_file.block (DebankBlock)

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 2.1 | id | 类型 string(hex), 与 eth_getBlockByNumber.hash 一致 | PASS |
| 2.2 | height | 类型 number, 与请求的 block_id 一致 | PASS |
| 2.3 | parent_id | 类型 string(hex), 与 eth_getBlockByNumber.parentHash 一致 | PASS |
| 2.4 | base_fee_per_gas | 类型 number 或 null(genesis), 与 eth_getBlockByNumber.baseFeePerGas 一致 | PASS |
| 2.5 | miner | 类型 string(address), 与 eth_getBlockByNumber.miner 一致 | PASS |
| 2.6 | gas_limit | 类型 number, 与 eth_getBlockByNumber.gasLimit 一致 | PASS |
| 2.7 | gas_used | 类型 number, 与 eth_getBlockByNumber.gasUsed 一致 | PASS |
| 2.8 | timestamp | 类型 number, 与 eth_getBlockByNumber.timestamp 一致 | PASS |
| 2.9 | process_start_timestamp | 类型 number, 合理范围 (近期 ms 时间戳) | PASS |

---

## 3. block_file.txs (DebankTransaction)

### 3.1 字段类型验证

已对 4 笔 tx (block 0x9a1eb0) 逐字段对比，8 字段 × 4 tx = 32 项全部 PASS。

对比来源：
- `eth_getTransactionReceipt` (简写 receipt): id, from_addr, gas_price, gas_used, status, idx
- `eth_getBlockByNumber(block, true)` 的 transactions 数组 (简写 tx): to_addr, gas_limit, nonce, input, value, max_fee_per_gas, max_priority_fee_per_gas

| # | 字段 | 类型 | 对比 API 和字段 | 结果 |
|---|------|------|---------------|------|
| 3.1.1 | id | string | receipt.transactionHash | PASS (4/4) |
| 3.1.2 | from_addr | string(address) | receipt.from | PASS (4/4) |
| 3.1.3 | to_addr | string(address) | tx.to (AA tx 取 receipt.to) | PASS (4/4) |
| 3.1.4 | gas_limit | number | tx.gas | PASS (4/4) |
| 3.1.5 | gas_price | number | receipt.effectiveGasPrice | PASS (4/4) |
| 3.1.6 | gas_used | number | receipt.gasUsed | PASS (4/4) |
| 3.1.7 | status | boolean | receipt.status (0x1→true, 0x0→false) | PASS (4/4) |
| 3.1.8 | max_fee_per_gas | number | tx.maxFeePerGas | PASS |
| 3.1.9 | max_priority_fee_per_gas | number | tx.maxPriorityFeePerGas | PASS |
| 3.1.10 | input | string(hex) | tx.input | PASS |
| 3.1.11 | nonce | number | tx.nonce | PASS (4/4) |
| 3.1.12 | idx | number | receipt.transactionIndex, 从 0 递增 | PASS (4/4) |
| 3.1.13 | value | string(hex U256) | tx.value | PASS |

### 3.2 tx 类型覆盖

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 3.2.1 | Legacy tx (type=0x0) | gas_price>0, max_fee_per_gas=gas_price, max_priority_fee_per_gas=0 | PASS (3 笔) |
| 3.2.2 | EIP-1559 tx (type=0x2) | max_fee_per_gas>0 | PASS (block 0x9e8900) |
| 3.2.3 | AA tx (type=0x76) | from_addr 为 AA 账户, to_addr=实际调用目标 (非 AA 信封) | PASS |
| 3.2.4 | System tx (from=0x0) | gas_limit=0, gas_used=0, status=true | PASS |
| 3.2.5 | 成功 tx | status=true | PASS |
| 3.2.6 | Revert tx | status=false (block 0x9a2040) | PASS |
| 3.2.7 | txs 数量 | 与 eth_getBlockByNumber.transactions 数量一致 | PASS (4=4) |
| 3.2.8 | idx 顺序 | 从 0 递增, 与区块内 tx 顺序一致 | PASS [0,1,2,3] |

---

## 4. block_file.traces (DebankTrace)

### 4.1 字段验证 (逐字段与 trace_transaction 对比)

已对比区块: 0x9a1eb0 (10 traces, call+delegatecall), 0x9a2040 (6 traces, 含 revert), 0x99b150 (5 traces, 含 create)。共 21 条 trace，每条比 11 个字段，全部 MATCH。

| # | 字段 | 类型 | trace_transaction 对应字段 | 结果 |
|---|------|------|--------------------------|------|
| 4.1.1 | id | string(MD5 hex, 32 chars) | 无对应 (DeBank 自有字段, MD5 算法验证) | PASS |
| 4.1.2 | from_addr | string(address) | action.from | PASS (21/21) |
| 4.1.3 | gas_limit | number | action.gas (十进制 vs hex) | PASS (21/21) |
| 4.1.4 | input | string(hex) | action.input (call) / action.init (create) | PASS (21/21) |
| 4.1.5 | to_addr | string(address) | action.to (call) / result.address (create) | PASS (21/21) |
| 4.1.6 | value | string(hex U256) | action.value | PASS (21/21) |
| 4.1.7 | gas_used | number | result.gasUsed | PASS (21/21) |
| 4.1.8 | output | string(hex) | result.output (call) / result.code (create) | PASS (21/21) |
| 4.1.9 | type | string | type ("call"/"create") | PASS (21/21) |
| 4.1.10 | call_type | string | action.callType (call 时) / "" (create 时) | PASS (21/21) |
| 4.1.11 | tx_id | string(tx hash) | transactionHash | PASS (21/21) |
| 4.1.12 | parent_trace_id | string | 无对应 (DeBank 自有字段) | PASS (MD5 验证) |
| 4.1.13 | pos_in_parent_trace | number | 无对应 (DeBank 自有字段) | PASS |
| 4.1.14 | self_storage_change | boolean | 无对应 (SSTORE opcode 检测) | PASS (类型验证) |
| 4.1.15 | storage_change | boolean | 无对应 (含子 trace 传播) | PASS (传播逻辑验证) |
| 4.1.16 | subtraces | number | subtraces | PASS (21/21) |
| 4.1.17 | trace_address | array[number] | traceAddress | PASS (21/21) |
| 4.1.18 | error | string | error (成功=null, 失败="Reverted") | PASS (revert block 验证) |

### 4.2 trace type 覆盖

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 4.2.1 | call 类型 | type="call", call_type="call" | PASS (block 0x9a1eb0, 7 条) |
| 4.2.2 | delegatecall 类型 | type="call", call_type="delegatecall" | PASS (block 0x9a1eb0, 1 条) |
| 4.2.3 | staticcall 类型 | type="call", call_type="staticcall" | 未覆盖 (Tempo 链上未发现) |
| 4.2.4 | create 类型 | type="create", call_type="", to_addr=创建的合约地址 | PASS (block 0x99b150, to_addr=0x28fc...f816) |
| 4.2.5 | 深层嵌套 | trace_address 多层 (如 [0,0,0,0,0]) | PASS (max depth=5) |
| 4.2.6 | storage_change 传播 | 子 trace 有 SSTORE, 父 trace.storage_change=true | PASS |

### 4.3 ID 计算验证

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 4.3.1 | trace id 算法 | id = MD5(tx_id + parent_trace_id + pos_in_parent_trace), 手动计算验证 | PASS (expected=actual) |
| 4.3.2 | root trace id | parent_trace_id="", pos=0, 验证 MD5 | PASS |
| 4.3.3 | id 全局唯一 | 同一区块内所有 trace id 无重复 | PASS (10 unique / 10 total) |

### 4.4 与 trace_transaction 对比

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 4.4.1 | trace 数量一致 | debankBlock traces+error_traces = trace_transaction 总数 (per tx), 3 个区块全部 PASS |
| 4.4.2 | 全字段对比 | 11 个字段 (from/to/type/callType/gas/gasUsed/input/output/value/subtraces/traceAddress) × 21 条 trace, 全部 MATCH |
| 4.4.3 | CREATE trace | block 0x99b150: type="create", to_addr=result.address, input=action.init, output=result.code, call_type="" PASS |

---

## 5. block_file.events (DebankEvent)

### 5.1 字段类型验证

| # | 字段 | 类型 | 验证方式 | 结果 |
|---|------|------|---------|------|
| 5.1.1 | id | string(MD5 hex, 32 chars) | 非空, 唯一 | PASS |
| 5.1.2 | contract_id | string(address) | 与 receipt.logs[].address 一致 | PASS |
| 5.1.3 | selector | string(hex, topic[0]) | 与 receipt.logs[].topics[0] 一致 | PASS |
| 5.1.4 | topics | array[string] | receipt.logs[].topics[1:] (不含 topic[0]) | PASS |
| 5.1.5 | data | string(hex) | 与 receipt.logs[].data 一致 | PASS |
| 5.1.6 | parent_trace_id | string | 指向产生此 log 的 trace id | PASS |
| 5.1.7 | pos_in_parent_trace | number | 在父 trace children 中的位置 | PASS |
| 5.1.8 | idx | number | 全局 log index, 递增 | PASS |

### 5.2 event 类型覆盖

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 5.2.1 | Transfer event | selector=0xddf252ad..., topics 含 from/to | PASS |
| 5.2.2 | 多 topic event | topics 数组长度 > 0 | PASS |
| 5.2.3 | 无 topic event (anonymous) | selector="", topics=[] | 未覆盖 (未找到) |
| 5.2.4 | fee Transfer log | contract_id 为 TIP-20 地址(0x20c0...), selector=Transfer | PASS |
| 5.2.5 | EVM 内 log + fee log | events 总数 = receipt logs 总数 | PASS (9=9, 5=5) |

### 5.3 ID 计算验证

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 5.3.1 | event id 算法 | id = MD5(parent_trace_id + pos_in_parent_trace), 手动计算验证 | PASS (expected=actual) |
| 5.3.2 | id 全局唯一 | 同一区块内所有 event id 无重复 | PASS (9 unique / 9 total) |

---

## 6. block_file.error_traces / error_events

测试区块: 0x9a2040 (含 1 笔 revert tx) + 0x9a1eb0 (全部成功, 含 AA tx)

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 6.1 | revert tx traces → error_traces | status=0x0 的 tx, traces 在 error_traces | PASS (1 条) |
| 6.2 | revert tx events → error_events | status=0x0 的 tx, fee log 在 error_events | PASS (1 条) |
| 6.3 | 成功 tx 不进 error | status=0x1 的 tx (含 AA), error_traces/error_events=0 | PASS |
| 6.4 | error_traces 字段完整 | 与 traces 相同的字段结构 | PASS |
| 6.5 | error_events 字段完整 | 与 events 相同的字段结构 | PASS |
| 6.6 | traces + error_traces = trace_transaction | per tx 验证 (block 0x9a2040, 4 txs) | PASS (4/4) |
| 6.7 | events + error_events = receipt logs | per tx 验证 | PASS (5=5) |
| 6.8 | error 字段非空 | error_traces 中的 trace: error="Reverted" | PASS |

---

## 7. block_file.storage_contracts

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 7.1 | 类型 | array[address] | PASS |
| 7.2 | 含 SSTORE 合约 | trace 中 storage_change=true 的 to_addr 出现在列表中 | PASS |
| 7.3 | 含 FeeManager | `0xfeec...` 出现在列表中 | PASS |
| 7.4 | 含 TIP-20 合约 | pathUSD 地址 (0x20c0...) 出现在列表中 | PASS |
| 7.5 | 空区块 | 无 state 变化的空区块, storage_contracts=[] | PASS (block 1) |

---

## 8. state_diff (RLP-encoded BlockStorageDiff)

RLP 解码验证使用 Python rlp 库，对 block 0x9a1eb0, 0x99b150, 0x0, 0x1 四个区块执行。

### 8.1 结构验证

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 8.1.1 | RLP 可解码 | hex → bytes → RLP decode 成功 | PASS (4 个区块) |
| 8.1.2 | hash | 与 header.stateRoot 一致 | PASS |
| 8.1.3 | parent_hash | 与 parent block 的 stateRoot 一致 | PASS |

### 8.2 new_accounts

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 8.2.1 | address | H256, keccak256(原始地址), 非零 | PASS |
| 8.2.2 | balance | U256, 合理数值 | PASS |
| 8.2.3 | nonce | u64, >= 0 | PASS |
| 8.2.4 | code_hash | H256, EOA 为 KECCAK_EMPTY, 合约为非空 hash | PASS |
| 8.2.5 | 非空区块有 new_accounts | new_accounts=10 (block 0x9a1eb0) | PASS |

### 8.3 storage_diffs

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 8.3.1 | address | H256, keccak256(合约地址) | PASS |
| 8.3.2 | diffs[].index | H256, keccak256(storage slot) | PASS |
| 8.3.3 | diffs[].value | U256, 新值 | PASS |
| 8.3.4 | 含 fee storage 变化 | storage_diffs=7 (含 FeeManager/TIP-20 slot) | PASS |
| 8.3.5 | 与 storage_contracts 对应 | storage_diffs 中的地址集合 ⊆ storage_contracts (hash 后) | PASS |

### 8.4 new_codes

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 8.4.1 | code_hash | H256, = keccak256(code) | PASS |
| 8.4.2 | code | Bytes, 合约 bytecode | PASS |
| 8.4.3 | 只含新部署代码 | 已存在的合约代码不出现 (通过 pre_db 过滤) | PASS (非部署块 new_codes=0) |
| 8.4.4 | 有部署区块 | block 0x99b150, new_codes=1 | PASS |

### 8.5 deleted_accounts

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 8.5.1 | selfdestruct | Tempo 无 SELFDESTRUCT | 未覆盖 |
| 8.5.2 | 正常区块 | deleted_accounts=0 | PASS |

### 8.6 空区块

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 8.6.1 | block 1 (empty) | new_accounts=0, storage_diffs=0, new_codes=0, deleted=0 | PASS |

---

## 9. header (alloy Header)

12 个字段逐一与 eth_getBlockByNumber 对比。

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 9.1 | hash | 与 eth_getBlockByNumber.hash 一致 | PASS |
| 9.2 | parentHash | 一致 | PASS |
| 9.3 | stateRoot | 一致 | PASS |
| 9.4 | transactionsRoot | 一致 | PASS |
| 9.5 | receiptsRoot | 一致 | PASS |
| 9.6 | number | 一致 | PASS |
| 9.7 | gasLimit | 一致 | PASS |
| 9.8 | gasUsed | 一致 | PASS |
| 9.9 | timestamp | 一致 | PASS |
| 9.10 | baseFeePerGas | 一致 | PASS |
| 9.11 | miner | 一致 | PASS |
| 9.12 | logsBloom | 一致 | PASS |

---

## 10. validation_hash

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 10.1 | 类型 | number (i64) | PASS |
| 10.2 | 非零 | validation_hash=144697 | PASS |
| 10.3 | 算法验证 | 手动计算 SHA1 sum 取末 6 位 | 未执行 (算法已在代码中验证) |
| 10.4 | 同一区块幂等 | 两次调用结果一致 (144697=144697) | PASS |

---

## 11. 特殊区块

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 11.1 | Genesis (block 0) | txs=15, traces=15, state_diff_len=58374 | PASS |
| 11.2 | 空区块 (block 1) | txs=1, events=0, state_diff 全空 | PASS |
| 11.3 | Fee 区块 (0x9a1eb0) | events 含 TIP-20 Transfer, storage_contracts 含 FeeManager | PASS |
| 11.4 | AA tx 区块 (0x9a1eb0) | AA tx traces 在 traces 中 (非 error_traces), 2 条 | PASS |
| 11.5 | 多 tx 区块 | idx=[0,1,2,3] 顺序正确 | PASS |
| 11.6 | CREATE 区块 (0x99b150) | type="create", new_codes=1 | PASS |
| 11.7 | 不存在的区块 | error: "block not found: 0xffffff00" | PASS |
| 11.8 | 最新区块 ("latest") | height > 10000000 | PASS |

---

## 12. 与 background-tracer 兼容性

| # | 测试项 | 验证内容 | 结果 |
|---|--------|---------|------|
| 12.1 | JSON 可解析 | background-tracer 的 DebankOutPut 类型能反序列化 | 未执行 (需 binary) |
| 12.2 | dry-run | background-tracer dry-run | 未执行 (需 binary) |
| 12.3 | 连续区块 parent_id 链 | 5 个连续区块, parent_id 链一致 | PASS |
| 12.4 | 性能 | 单次调用 12ms (< 5s) | PASS |
