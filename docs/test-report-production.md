# DeBank 自定义 RPC 生产环境测试报告

## 测试环境

- 节点: `archive.tempo.blockchain` (生产 Archive 节点组, 3 实例负载均衡)
- 版本: `tempo/v1.4.3-VERGEN_/aarch64-unknown-linux-gnu`
- 网络: Tempo 主网 (chain ID 4217)
- 对照: 官方 RPC `https://rpc.tempo.xyz` (`tempo/v1.4.3-a35c7d1/x86_64-unknown-linux-gnu`, 同版本)
- 访问方式: SSH nodectl 跳板机, RPC 端口 80
- 日期: 2026-03-20

---

## 1. eth_multiCall

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 1.1 | 基础 ERC-20 balanceOf | **PASS** | code=0, camelCase 字段正确, gasUsed=273644, fromCache=false |
| 1.2 | 批量调用 (3 笔) | **PASS** | 返回 3 条 result, codes=[0,0,0] |
| 1.3 | 0xeeee balanceOf | **PASS** | code=0, gasUsed=0 (Tempo 无 native token, 符合预期) |
| 1.4 | 0xeeee decimals/name/symbol | **PASS** | decimals=18, name="ETH", symbol="ETH", 全部 code=0 |
| 1.5 | 0xeeee totalSupply | **PASS** | 返回 1 |
| 1.6 | 0xeeee 未知 selector | **PASS** | code=-40001, err="method not found" |
| 1.7 | fast_fail | **PASS** | 第一笔 code=-40014 (EVMReverted), 第二笔 code=-40015 "skipped due to fast_fail" |
| 1.8 | revert (无 fast_fail) | **PASS** | code=-40014, err="Reason Unknown", stats.success=false |
| 1.9 | 指定历史区块 0x9b2006 | **PASS** | stats.blockNum=10166278 匹配 |
| 1.10 | 空请求 [] | **PASS** | results=[], stats 正常返回 |
| 1.11 | 极早期块 - block 0 (genesis) | **PASS** | code=0, blockTime=0 |
| 1.11b | 极早期块 - block 1 | **PASS** | code=0, 正常返回 |
| 1.11c | 极早期块 - ERC-20 @ block 1 | **PASS** | code=-40014, 合约未部署, revert 符合预期 |
| 1.12 | useParallel=true | **PASS** | 不报错, 返回 2 条结果正常 |
| 1.13 | disableCache=true | **PASS** | stats.cacheEnabled=false |
| 1.14 | SingleCallResult 字段类型验证 | **PASS** | code:number, err:string, fromCache:boolean, result:string(hex), gasUsed:number(>0), timeCost:number(>0) |
| 1.15 | MultiCallStats 字段类型验证 | **PASS** | blockNum:number, blockHash:string(非空), blockTime:number, success:boolean, cacheEnabled:boolean |
| 1.16 | state_overrides 注入 code | **PASS** | 返回 0x2a (42); 对照组 (无 overrides) 返回 0x (空) |
| 1.17 | block_overrides | **PASS** | 覆盖 number/time/baseFeePerGas, code=0 |
| 1.18 | blockHash 指定区块 | **PASS** | blockNum=10166278 匹配 |
| 1.19 | per-call gas limit | **PASS** | gas=0x100000 正常执行, gasUsed=273270 |
| 1.20 | 不存在的区块 | **PASS** | code=-32001 "block not found: 0xffffff00" |
| 1.21 | EVMCancelled/Halt (无限循环) | **PASS** | code=-40013, err="Halted: Ethereum(OutOfGas(Basic))", gasUsed=50000000 |
| 1.22 | Revert 带 reason string | **PASS** | code=-40014, err="revert: test" |
| 1.24 | 混合成功+失败时 stats.success | **PASS** | codes=[0,-40014,0], stats.success=false |
| 1.26 | per-call from 字段 | **PASS** | code=0, 执行正常 |
| 1.27 | per-call value 字段 | **PASS** | RPC 错误 "value transfer not allowed" (Tempo 链特性, 符合预期) |

**注意**: 生产环境的 `eth_multiCall` 参数为 **positional** 格式: `[calls, blockId, fast_fail, use_parallel, disable_cache, state_overrides, block_overrides]`, 不支持 named object。

---

## 2. pre_traceMany

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 2.1 | 基础 balanceOf trace | **PASS** | traceLen=1, logsLen=0, gasUsed=23644, error=null |
| 2.2 | ERC-20 transfer trace | **PASS** | traceLen=1, logsLen=1 (Transfer event, topic=0xddf252ad), gasUsed=50546 |
| 2.3 | 多笔顺序执行 | **PASS** | 第一笔 transfer 成功 (logs=1), 第二笔 balanceOf 能看到变更后的余额 |
| 2.4 | revert | **PASS** | error.code=1002, error.msg="revert", gasUsed=0 |
| 2.5 | gas 不足 (gas=0x10) | **PASS** | code=1000, msg="insufficient gas for intrinsic cost: gas_limit 16 < intrinsic_gas 21064" |
| 2.6 | 指定历史 block_id | **PASS** | traceLen=1, gasUsed=273644, error=null |
| 2.7 | 空交易列表 [] | **PASS** | 返回 [] |
| 2.8 | Log 字段完整性验证 | **PASS** | address/topics(3)/data/blockHash/blockNumber/blockTimestamp/transactionHash 全部存在, transactionIndex=0x0, logIndex=0x0, removed=false |
| 2.9 | Parity trace 字段完整性 | **PASS** | action: from/to/gas/input/value/callType 全部存在, result: gasUsed/output 存在, blockHash/blockNumber/transactionHash 非空, subtraces=0, traceAddress=[], type="call" |
| 2.10 | PreResult 成功时 error 字段省略 | **PASS** | 成功时 JSON 中无 error 字段 (skip_serializing_if 生效), gasUsed>0 |
| 2.11 | PreResult 失败时 error 字段类型 | **PASS** | error: object, code: number(1002), msg: string("revert"), gasUsed=0, trace=[], logs=[] |
| 2.12 | state_overrides 注入 code | **PASS** | traceLen=1, gasUsed=21018, error=null |
| 2.13 | block_overrides | **PASS** | traceLen=1, error=null |
| 2.14 | revert 后继续执行 | **PASS** | 第一笔 revert (code=1002), 第二笔 balanceOf 正常 (gasUsed=23644) |
| 2.15 | 成功->revert->查询 混合场景 | **PASS** | transfer(成功,logs=1) -> transferFrom(revert,code=1002) -> balanceOf(成功), state 可见性正确 |
| 2.16 | AA tx (type=0x76) 参数模拟 | **PASS** | 使用链上真实 AA tx 的 inner call 参数, traceLen=7, logsLen=4, gasUsed=370232 |
| 2.17 | native value 转账 trace | **不适用** | Tempo 禁止 native value transfer |
| 2.18 | from/nonce/gasPrice 可选字段 | **PASS** | gasUsed=23270, error=null |
| 2.19 | nonce 连续/不连续 | **PASS** | nonce=0 和 nonce=0x99 均正常执行, reth 不校验 nonce |
| 2.20 | insufficient funds | **不适用** | Tempo 无 native token, 无法触发余额不足 |

---

## 3. trace_transaction

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 3.1 | AA tx (type=0x76) trace | **PASS** | 8 条 trace, callType 含 call+staticcall, 字段完整 |
| 3.2 | 合约交互 tx (type=0x2) | **PASS** | 19 条 trace, 与官方 RPC 完全一致 |
| 3.3 | revert tx (status=0x0) | **PASS** | tx `0xbd586e05...`, inner trace error="Reverted", ERC-20 transfer 余额不足 |
| 3.4 | 不存在的 tx hash | **PASS** | 返回 result=null |
| 3.5 | delegatecall 类型 trace | **PASS** | tx `0xd86f6e09...` (block 0x9a1eb0), callType="delegatecall", from/to 字段完整 |
| 3.6 | 深层调用链 (nested traceAddress) | **PASS** | 8 条 trace, max_depth=3, traceAddress 从 [] 到 [0,2,2], 层级递增正确 |
| 3.7 | create 类型 trace | **PASS** | tx `0x62dd2453...` (block 0x99b150), type="create", createdAddr=0x28fc...f816, init 含完整 bytecode |
| 3.8 | native value transfer | **不适用** | Tempo 无 native gas token |
| 3.9 | transactionPosition 正确性 | **PASS** | block 0x9a1eb0 含 4 笔 tx, position 0→1→2→3 与 eth_getBlockByNumber 顺序完全一致 |
| 3.10 | 早期区块 trace | **PASS** | block 1/2/3/10/100/1000/10000 的 tx trace 均正常返回 |

---

## 4. 与官方 RPC 对比

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 4.1 | eth_chainId | **一致** | 均返回 0x1079 (4217) |
| 4.2 | eth_getBalance (latest + historical) | **一致** | latest 和 0x9b2006 余额均一致 |
| 4.3 | eth_estimateGas | **一致** | 均返回 0x5c37 |
| 4.4 | eth_call (historical) | **一致** | 同一区块同一请求返回值完全相同 |
| 4.5 | 区块数据一致性 | **一致** | hash/stateRoot/transactionsRoot/receiptsRoot/gasUsed 全部一致 |
| 4.6 | eth_getTransactionReceipt | **一致** | status/gasUsed/blockHash/cumulativeGasUsed/logsCount 全部一致 |
| 4.7 | trace_transaction 单笔对比 | **一致** | AA tx (type=0x76) 与官方 RPC 完全相同 |
| 4.8 | trace_transaction 批量对比 (block 0x9a1eb0, 4 txs) | **4/4 一致** | |
| 4.9 | trace_transaction 广泛对比 (10 区块, 21 笔 tx) | **21/21 一致** | 覆盖 type=0x0/0x2/0x76, 含 delegatecall/create |
| 4.10 | trace_transaction 早期区块对比 (block 1~10000) | **7/7 一致** | |

---

## 5. 压力测试

### eth_multiCall 批量

| 请求数 | 耗时 | 错误数 | 结果 |
|--------|------|--------|------|
| 100 | 13ms | 0 | **PASS** |
| 500 | 19ms | 0 | **PASS** |
| 1000 | 24ms | 0 | **PASS** |
| 5000 | 63ms | 0 | **PASS** |

### pre_traceMany 批量

| 请求数 | 耗时 | 错误数 | 结果 |
|--------|------|--------|------|
| 100 | 15ms | 0 | **PASS** |
| 500 | 30ms | 0 | **PASS** |
| 5000 | 395ms | 0 | **PASS** |

### 并发测试

| 并发数 | 每请求笔数 | 耗时 | HTTP 状态 | 结果 |
|--------|-----------|------|-----------|------|
| 10 | 1 | 42ms | 全部 200 | **PASS** |

---

## 补充说明

### 与开发环境测试的差异

1. **RPC 端口**: 生产环境通过端口 80 (负载均衡/反向代理), 开发环境直接 8545
2. **架构**: 生产 aarch64 (ARM), 官方 x86_64

### Tempo 链特性导致的"不适用"项

与开发环境一致:
- **native value transfer** (2.17, 3.8): Tempo 无传统 native gas token, EVM 层禁止 value transfer
- **insufficient funds** (2.20): 无 native token 余额场景

---

## 总结

- **DeBank 自定义 RPC 全部功能正常**: eth_multiCall (27 项全部 PASS) 和 pre_traceMany (18 项 PASS + 2 不适用)
- **与官方 RPC 数据完全一致**: 28/28 笔 trace_transaction 对比全部一致, 标准 API (chainId/balance/estimateGas/call/receipt/block) 全部一致
- **trace_transaction 全部功能正常**: 覆盖 call/delegatecall/staticcall/create, 深层调用链, 早期区块, revert tx
- **压力测试通过**: eth_multiCall 5000 笔 63ms, pre_traceMany 5000 笔 395ms, 10 并发正常
- **生产节点同步正常**: 最新区块 ~10,308,000+, 与链头同步
