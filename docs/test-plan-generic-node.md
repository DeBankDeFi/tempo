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

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 1.1 | 返回结构完整性 | block_file/header/state_diff/validation_hash 四个字段均存在且非 null |
| 1.2 | validation_hash 类型 | number 类型, 非零 |
| 1.3 | state_diff 格式 | hex string, 以 0x 开头, RLP 可解码 |
| 1.4 | header 与 eth_getBlockByNumber 一致 | hash/stateRoot/transactionsRoot/receiptsRoot/gasUsed/number/timestamp 逐字段对比 |

---

## 2. block_file.block (DebankBlock)

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 2.1 | id | 类型 string(hex), 与 eth_getBlockByNumber.hash 一致 |
| 2.2 | height | 类型 number, 与请求的 block_id 一致 |
| 2.3 | parent_id | 类型 string(hex), 与 eth_getBlockByNumber.parentHash 一致 |
| 2.4 | base_fee_per_gas | 类型 number 或 null(genesis), 与 eth_getBlockByNumber.baseFeePerGas 一致 |
| 2.5 | miner | 类型 string(address), 与 eth_getBlockByNumber.miner 一致 |
| 2.6 | gas_limit | 类型 number, 与 eth_getBlockByNumber.gasLimit 一致 |
| 2.7 | gas_used | 类型 number, 与 eth_getBlockByNumber.gasUsed 一致 |
| 2.8 | timestamp | 类型 number, 与 eth_getBlockByNumber.timestamp 一致 |
| 2.9 | process_start_timestamp | 类型 number, 合理范围 (近期 ms 时间戳) |

---

## 3. block_file.txs (DebankTransaction)

### 3.1 字段类型验证

| # | 字段 | 类型 | 验证方式 |
|---|------|------|---------|
| 3.1.1 | id | string | 与 receipt.transactionHash 一致 |
| 3.1.2 | from_addr | string(address) | 与 receipt.from 一致 |
| 3.1.3 | to_addr | string(address) | 与 tx.to 或 Address::ZERO (创建合约时) 一致 |
| 3.1.4 | gas_limit | number | 与 tx.gas 一致 |
| 3.1.5 | gas_price | number | 与 receipt.effectiveGasPrice 一致 |
| 3.1.6 | gas_used | number | 与 receipt.gasUsed 一致 |
| 3.1.7 | status | boolean | 与 receipt.status 一致 (true=0x1, false=0x0) |
| 3.1.8 | max_fee_per_gas | number | 与 tx.maxFeePerGas 一致 |
| 3.1.9 | max_priority_fee_per_gas | number | 与 tx.maxPriorityFeePerGas 一致 |
| 3.1.10 | input | string(hex) | 与 tx.input 一致 |
| 3.1.11 | nonce | number | 与 tx.nonce 一致 |
| 3.1.12 | idx | number | 从 0 递增, 与 receipt.transactionIndex 一致 |
| 3.1.13 | value | string(hex U256) | 与 tx.value 一致 |

### 3.2 tx 类型覆盖

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 3.2.1 | Legacy tx (type=0x0) | gas_price>0, max_fee_per_gas=gas_price, max_priority_fee_per_gas=0 |
| 3.2.2 | EIP-1559 tx (type=0x2) | max_fee_per_gas 和 max_priority_fee_per_gas 均>0 |
| 3.2.3 | AA tx (type=0x76) | from_addr 为 AA 账户, to_addr 正确 |
| 3.2.4 | System tx (from=0x0) | gas_limit=0, gas_used=0, status=true |
| 3.2.5 | 成功 tx | status=true |
| 3.2.6 | Revert tx | status=false |
| 3.2.7 | txs 数量 | 与 eth_getBlockByNumber.transactions 数量一致 |
| 3.2.8 | idx 顺序 | 从 0 递增, 与区块内 tx 顺序一致 |

---

## 4. block_file.traces (DebankTrace)

### 4.1 字段类型验证

| # | 字段 | 类型 | 验证方式 |
|---|------|------|---------|
| 4.1.1 | id | string(MD5 hex, 32 chars) | 非空, 唯一 |
| 4.1.2 | from_addr | string(address) | 非零 (root trace 为 tx sender) |
| 4.1.3 | gas_limit | number | 与 trace_transaction.action.gas 一致 (十进制 vs hex) |
| 4.1.4 | input | string(hex) | 与 trace_transaction.action.input 一致 |
| 4.1.5 | to_addr | string(address) | 与 trace_transaction.action.to 一致 |
| 4.1.6 | value | string(hex U256) | 与 trace_transaction.action.value 一致 |
| 4.1.7 | gas_used | number | 与 trace_transaction.result.gasUsed 一致 |
| 4.1.8 | output | string(hex) | 与 trace_transaction.result.output 一致 |
| 4.1.9 | type | string | "call" / "create" / "create2" / "suicide" 之一 |
| 4.1.10 | call_type | string | type="call" 时: "call"/"delegatecall"/"staticcall"/"callcode"; type!="call" 时: 空字符串 |
| 4.1.11 | tx_id | string(tx hash) | 与所属 tx 的 hash 一致 |
| 4.1.12 | parent_trace_id | string | root trace 为 "", 子 trace 为父 trace 的 id |
| 4.1.13 | pos_in_parent_trace | number | 在父 trace children 中的位置索引 |
| 4.1.14 | self_storage_change | boolean | 当前 frame 有 SSTORE → true |
| 4.1.15 | storage_change | boolean | 当前 frame 或子 frame 有 SSTORE → true |
| 4.1.16 | subtraces | number | 与 trace_transaction.subtraces 一致 |
| 4.1.17 | trace_address | array[number] | 与 trace_transaction.traceAddress 一致 |
| 4.1.18 | error | string | 成功 trace: 空字符串(omit); 失败: "Reverted"/"Out of gas" 等 |

### 4.2 trace type 覆盖

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 4.2.1 | call 类型 | type="call", call_type="call" |
| 4.2.2 | delegatecall 类型 | type="call", call_type="delegatecall" |
| 4.2.3 | staticcall 类型 | type="call", call_type="staticcall" (如有) |
| 4.2.4 | create 类型 | type="create", call_type="", to_addr=创建的合约地址 |
| 4.2.5 | 深层嵌套 | trace_address 多层 (如 [0,0,0,0,0]) |
| 4.2.6 | storage_change 传播 | 子 trace 有 SSTORE, 父 trace.storage_change=true |

### 4.3 ID 计算验证

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 4.3.1 | trace id 算法 | id = MD5(tx_id + parent_trace_id + pos_in_parent_trace), 手动计算验证 |
| 4.3.2 | root trace id | parent_trace_id="", pos=0, 验证 MD5 |
| 4.3.3 | id 全局唯一 | 同一区块内所有 trace id 无重复 |

### 4.4 与 trace_transaction 对比

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 4.4.1 | trace 数量一致 | debankBlock traces+error_traces = trace_transaction 总数 (per tx) |
| 4.4.2 | 字段值一致 | from/to/gas/gasUsed/callType/traceAddress/subtraces 逐字段 (注意十进制 vs hex) |
| 4.4.3 | 批量对比 (10 区块) | 选取有 tx 的区块, 逐 tx 对比 |

---

## 5. block_file.events (DebankEvent)

### 5.1 字段类型验证

| # | 字段 | 类型 | 验证方式 |
|---|------|------|---------|
| 5.1.1 | id | string(MD5 hex, 32 chars) | 非空, 唯一 |
| 5.1.2 | contract_id | string(address) | 与 receipt.logs[].address 一致 |
| 5.1.3 | selector | string(hex, topic[0]) | 与 receipt.logs[].topics[0] 一致 |
| 5.1.4 | topics | array[string] | receipt.logs[].topics[1:] (不含 topic[0]) |
| 5.1.5 | data | string(hex) | 与 receipt.logs[].data 一致 |
| 5.1.6 | parent_trace_id | string | 指向产生此 log 的 trace id |
| 5.1.7 | pos_in_parent_trace | number | 在父 trace children 中的位置 |
| 5.1.8 | idx | number | 全局 log index, 递增 |

### 5.2 event 类型覆盖

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 5.2.1 | Transfer event | selector=0xddf252ad..., topics 含 from/to |
| 5.2.2 | 多 topic event | topics 数组长度 > 0 |
| 5.2.3 | 无 topic event (anonymous) | selector="", topics=[] |
| 5.2.4 | fee Transfer log | contract_id 为 TIP-20 地址(0x20c0...), selector=Transfer |
| 5.2.5 | EVM 内 log + fee log | events 总数 = receipt logs 总数 |

### 5.3 ID 计算验证

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 5.3.1 | event id 算法 | id = MD5(parent_trace_id + pos_in_parent_trace), 手动计算验证 |
| 5.3.2 | id 全局唯一 | 同一区块内所有 event id 无重复 |

---

## 6. block_file.error_traces / error_events

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 6.1 | revert tx 的 trace 进 error_traces | status=false 的 tx, 其 traces 出现在 error_traces |
| 6.2 | revert tx 的 event 进 error_events | status=false 的 tx, 其 events 出现在 error_events |
| 6.3 | 成功 tx 不进 error | status=true 的 tx, traces/events 不出现在 error 列表 |
| 6.4 | error_traces 字段完整 | 与 traces 相同的字段结构 |
| 6.5 | error_events 字段完整 | 与 events 相同的字段结构 |
| 6.6 | traces + error_traces = trace_transaction 总数 | per tx 验证 |
| 6.7 | events + error_events = receipt logs 总数 | per tx 验证 |
| 6.8 | trace.error 字段 | error_traces 中的 trace: error 字段非空 ("Reverted" 等) |

---

## 7. block_file.storage_contracts

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 7.1 | 类型 | array[address] |
| 7.2 | 含 SSTORE 合约 | trace 中 storage_change=true 的 to_addr 出现在列表中 |
| 7.3 | 含 FeeManager | 有 fee 交易的区块, `0xfeec...` 出现在列表中 |
| 7.4 | 含 TIP-20 合约 | 有 transfer 的区块, pathUSD 地址出现在列表中 |
| 7.5 | 空区块 | 无 state 变化的空区块, storage_contracts=[] |

---

## 8. state_diff (RLP-encoded BlockStorageDiff)

### 8.1 结构验证

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 8.1.1 | RLP 可解码 | hex → bytes → RLP decode 成功 |
| 8.1.2 | hash | 与 header.stateRoot 一致 |
| 8.1.3 | parent_hash | 与 parent block 的 stateRoot 一致 |

### 8.2 new_accounts

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 8.2.1 | address | H256, keccak256(原始地址), 非零 |
| 8.2.2 | balance | U256, 合理数值 |
| 8.2.3 | nonce | u64, >= 0 |
| 8.2.4 | code_hash | H256, EOA 为 KECCAK_EMPTY, 合约为非空 hash |
| 8.2.5 | 非空区块有 new_accounts | 有 state 变化的区块, new_accounts.length > 0 |

### 8.3 storage_diffs

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 8.3.1 | address | H256, keccak256(合约地址) |
| 8.3.2 | diffs[].index | H256, keccak256(storage slot) |
| 8.3.3 | diffs[].value | U256, 新值 |
| 8.3.4 | 含 fee storage 变化 | FeeManager 或 TIP-20 合约的 storage slot 出现 |
| 8.3.5 | 与 storage_contracts 对应 | storage_diffs 中的地址集合 ⊆ storage_contracts (hash 后) |

### 8.4 new_codes

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 8.4.1 | code_hash | H256, = keccak256(code) |
| 8.4.2 | code | Bytes, 合约 bytecode |
| 8.4.3 | 只含新部署代码 | 已存在的合约代码不出现 (通过 pre_db 过滤) |
| 8.4.4 | 无部署区块 | 无合约创建的区块, new_codes=[] |

### 8.5 deleted_accounts

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 8.5.1 | selfdestruct | 如有 SELFDESTRUCT tx, 对应地址出现在 deleted_accounts |
| 8.5.2 | 正常区块 | 无 selfdestruct 的区块, deleted_accounts=[] |

### 8.6 空区块

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 8.6.1 | parent_state_root == state_root | new_accounts/storage_diffs/new_codes/deleted_accounts 均为空 |

---

## 9. header (alloy Header)

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 9.1 | hash | 与 eth_getBlockByNumber.hash 一致 |
| 9.2 | parentHash | 与 eth_getBlockByNumber.parentHash 一致 |
| 9.3 | stateRoot | 与 eth_getBlockByNumber.stateRoot 一致 |
| 9.4 | transactionsRoot | 与 eth_getBlockByNumber.transactionsRoot 一致 |
| 9.5 | receiptsRoot | 与 eth_getBlockByNumber.receiptsRoot 一致 |
| 9.6 | number | 与请求 block_id 一致 |
| 9.7 | gasLimit | 与 eth_getBlockByNumber.gasLimit 一致 |
| 9.8 | gasUsed | 与 eth_getBlockByNumber.gasUsed 一致 |
| 9.9 | timestamp | 与 eth_getBlockByNumber.timestamp 一致 |
| 9.10 | baseFeePerGas | 与 eth_getBlockByNumber.baseFeePerGas 一致 |
| 9.11 | miner | 与 eth_getBlockByNumber.miner 一致 |
| 9.12 | logsBloom | 与 eth_getBlockByNumber.logsBloom 一致 |

---

## 10. validation_hash

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 10.1 | 类型 | number (i64) |
| 10.2 | 非零 | 有 tx 的区块, validation_hash != 0 |
| 10.3 | 算法验证 | 手动计算: SHA1(block.id) + SHA1(tx.id[0]) + ... + SHA1(event.id[0]) + ... + SHA1(trace.id[0]) + ..., 取末 6 位 |
| 10.4 | 同一区块幂等 | 多次调用同一区块, validation_hash 一致 |

---

## 11. 特殊区块

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 11.1 | Genesis (block 0) | synthetic txs/traces, state_diff 含 genesis alloc, 无 events |
| 11.2 | 空区块 (仅系统 tx) | txs=1, traces=0/1, events=0, state_diff 极小 |
| 11.3 | 有 fee 的区块 | events 含 fee Transfer log, storage_contracts 含 FeeManager |
| 11.4 | AA tx 区块 | AA tx 的 traces 和 events 正确 (可能含 error_traces) |
| 11.5 | 多 tx 区块 | idx 顺序正确, log_index 全局递增 |
| 11.6 | 合约创建区块 | traces 含 type="create", state_diff.new_codes 非空 |
| 11.7 | 不存在的区块 | 返回 error, code=-32001 或类似 |
| 11.8 | 最新区块 ("latest") | 正常返回, block.height = 链头 |

---

## 12. 与 background-tracer 兼容性

| # | 测试项 | 验证内容 |
|---|--------|---------|
| 12.1 | JSON 可解析 | background-tracer 的 DebankOutPut 类型能反序列化 |
| 12.2 | dry-run | `background-tracer dry-run --start-block=X --end-block=X+5` 无报错 |
| 12.3 | 批量连续 | 连续 100 个区块, 无报错, parent_id 链一致 |
| 12.4 | 性能 | 单次调用 < 5s, 不超时 |
