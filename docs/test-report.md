# DeBank 自定义 RPC 测试报告

## 测试环境

- 机器: `blockchain-misc-x3` (x86_64, Ubuntu 20.04)
- 镜像: `blockchain/kava-x:amd64-6553257` (tempo v1.4.3)
- 网络: Tempo 主网 (chain ID 4217)
- 对照: 官方 RPC `https://rpc.tempo.xyz` (tempo v1.4.3, 同版本)
- 浏览器: `https://explore.tempo.xyz`
- 日期: 2026-03-19

---

## 1. eth_multiCall

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 1.1 | 基础 ERC-20 balanceOf | PASS | code=0, camelCase 字段正确, results+stats 结构完整 |
| 1.2 | 批量调用 (3 笔) | PASS | 返回 3 条 result, 数量与请求一致 |
| 1.3 | 0xeeee balanceOf | PASS | code=0, balance=0 (Tempo 无 native token, 符合预期), gasUsed=0 |
| 1.4 | 0xeeee decimals | PASS | 返回 18 |
| 1.4 | 0xeeee name | PASS | ABI decode = "ETH" |
| 1.4 | 0xeeee symbol | PASS | ABI decode = "ETH" |
| 1.5 | 0xeeee totalSupply | PASS | 返回 1 |
| 1.6 | 0xeeee 未知 selector | PASS | code=-40001 (NativeMethodNotFound), err="method not found" |
| 1.7 | fast_fail | PASS | 第一笔 code=-40014 (EVMReverted), 第二笔 code=-40015 (EVMFastFailed), err="skipped due to fast_fail" |
| 1.8 | revert (无 fast_fail) | PASS | code=-40014, err="Reason Unknown", stats.success=false |
| 1.9 | 指定历史区块 | PASS | stats.blockNum=10166278 匹配请求的 0x9b2006 |
| 1.10 | 空请求 [] | PASS | results=[], stats 正常返回 |
| 1.11 | 极早期块 - 0xeeee @ block 0 (genesis) | PASS | code=0, blockTime=0, 创世块正常查询 |
| 1.12 | 极早期块 - 0xeeee @ block 1 | PASS | code=0, 正常返回 |
| 1.13 | 极早期块 - ERC-20 @ block 1 (合约未部署) | PASS | code=-40014 (EVMReverted), 合约尚未部署, revert 符合预期 |
| 1.14 | SingleCallResult 字段类型验证 | PASS | code: number(0), err: string(""), fromCache: boolean(false), result: string(hex), gasUsed: number(>0), timeCost: number(>0) |
| 1.15 | MultiCallStats 字段类型验证 | PASS | blockNum: number, blockHash: string(非空), blockTime: number, success: boolean(true), cacheEnabled: boolean(true) |
| 1.16 | state_overrides 注入 code | PASS | 向空地址注入合约 code (返回 42), 调用返回 0x2a; 对照组 (无 overrides) 返回 0x (空), 验证 overrides 生效 |
| 1.17 | block_overrides | PASS | 覆盖 number/time/baseFeePerGas, 调用正常执行, code=0 |
| 1.18 | blockHash 指定区块 | PASS | 通过 blockHash 指定历史区块, blockNum=10166278 匹配, BlockId hash 路径正常 |
| 1.19 | per-call gas limit | PASS | gas=0x100000 正常执行 gasUsed=271216; gas 低于 intrinsic cost 时返回 RPC 错误 (与 eth_call 行为一致) |
| 1.20 | 不存在的区块 | PASS | 不存在的 blockHash 和过高的 blockNumber 均返回 code=-32001 "block not found" |
| 1.21 | EVMCancelled / Halt (-40013) | PASS | state_overrides 注入无限循环合约 (0x5b600056), code=-40013, err="Halted: Ethereum(OutOfGas(Basic))", gasUsed=全部消耗 |
| 1.22 | disableCache=true | PASS | stats.cacheEnabled=false, 参数生效 |
| 1.23 | Revert 带 reason string | PASS | state_overrides 注入 revert("test") 合约, code=-40014, err="revert: test", reason 正确解码 |
| 1.24 | 混合成功+失败时 stats.success | PASS | 3 笔 (成功+revert+成功), stats.success=false, 第 1/3 笔 code=0, 第 2 笔 code=-40014 |
| 1.25 | useParallel=true | PASS | 传入 useParallel=true 不报错, 返回 2 条结果正常 (实现中该参数被忽略) |
| 1.26 | per-call from 字段 | PASS | 指定 from 地址, 执行正常 code=0 |
| 1.27 | per-call value 字段 | PASS | 带 value>0, 执行正常 code=0 |

---

## 2. pre_traceMany

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 2.1 | 基础 balanceOf trace | PASS | traceLen=1, logsLen=0, gasUsed=23644, error=null |
| 2.2 | ERC-20 transfer trace | PASS | traceLen=1 (callType=call), logsLen=1 (Transfer event, topic=0xddf252ad), gasUsed=50546 |
| 2.8 | Log 字段完整性验证 | PASS | Transfer event log 全部字段正确: address=合约地址, topic[0]=Transfer sig, topic[1]=from, topic[2]=to, data=金额, blockHash/blockNumber/blockTimestamp/transactionHash 非空, transactionIndex=0x0, logIndex=0x0, removed=false |
| 2.3 | 多笔顺序执行 | PASS | 第一笔 transfer 成功 (logs=1), 第二笔 balanceOf 能看到变更后的余额 |
| 2.4 | revert | PASS | error.code=1002 (Reverted), error.msg="revert", gasUsed=0 |
| 2.5 | gas 不足 (gas=0x10) | PASS | gas 低于 intrinsic cost 时: code=1000 (UnKnown), 在 inspect() 层报错; gas 够 intrinsic 但 EVM 内耗尽时: code=1001, msg="halt: Ethereum(OutOfGas(Basic))"。两种路径均符合预期 |
| 2.6 | 指定历史 block_id | PASS | traceLen=1, gasUsed=23644, error=null |
| 2.7 | 空交易列表 [] | PASS | 返回 [] |
| 2.8 | Log 字段完整性 | PASS | Transfer event log 全部字段正确: address=合约地址, topic[0]=Transfer sig, topic[1]=from, topic[2]=to, data=金额, blockHash/blockNumber/blockTimestamp/transactionHash 非空, transactionIndex=0x0, logIndex=0x0, removed=false |
| 2.9 | Parity trace 字段完整性 | PASS | action: from/to/gas/input/value/callType 全部存在且类型正确; result: gasUsed/output 存在; blockHash/blockNumber/transactionHash/transactionPosition 非空; subtraces=0, traceAddress=[], type="call" |
| 2.10 | PreResult 成功时 error 字段省略 | PASS | 成功时 JSON 中无 error 字段 (skip_serializing_if 生效), gasUsed>0, trace/logs 为数组 |
| 2.11 | PreResult 失败时 error 字段类型 | PASS | error 为 object, error.code 为 number (1002), error.msg 为 string ("revert"), gasUsed=0, trace=[], logs=[] |
| 2.12 | state_overrides 注入 code | PASS | 向空地址注入合约 code, trace 正常执行, traceLen=1, gasUsed=21018, error=null |
| 2.13 | block_overrides | PASS | 覆盖 number/time/baseFeePerGas, trace 正常执行, traceLen=1, error=null |
| 2.14 | revert 后继续执行 | PASS | 第一笔 revert, 第二笔 balanceOf 正常执行, gasUsed 与单独调用一致, revert 的 state 变更被正确回滚 |
| 2.15 | 成功->revert->查询 混合场景 | PASS | transfer(成功,logs=1) -> transferFrom(revert,code=1002) -> balanceOf(成功), 第一笔 state 保留, 第二笔正确回滚, 第三笔能查到第一笔的变更 |
| 2.16 | AA tx (type=0x76) 参数模拟 | PASS | 使用链上真实 AA tx 的 from/to/data 构造请求, traceLen=1, logsLen=2 (Transfer + 自定义事件), gasUsed=550287, trace 字段完整 |
| 2.17 | native value 转账 trace | **不适用** | Tempo 禁止 native value transfer ("value transfer not allowed"), 无 native gas token, 此场景不存在 |
| 2.18 | from/nonce/gasPrice 可选字段 | PASS | 携带 from/nonce/gasPrice 字段, 执行正常 gasUsed=271064, error=null |
| 2.19 | nonce 连续递增校验 | PASS | 连续 nonce (0,1) 和不连续 nonce (0,0x99) 均正常执行。reth 的 prepare_call_env 不做 nonce 校验 (与 eth_call 一致) |
| 2.20 | insufficient funds (code=1001) | **不适用** | Tempo 禁止 value transfer, 无法触发余额不足场景。所有 value 相关错误在 inspect() 层返回 code=1000 |

---

## 3. trace_transaction

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 3.1 | 合约 tx (ERC-20 transfer) | PASS | type=CALL, gasUsed=0x57da, error="execution reverted" |
| 3.2 | 合约交互 tx | PASS | 与官方 RPC 完全一致 |
| 3.3 | revert tx (status=0x0) | PASS | error="execution reverted", 与官方 RPC 完全一致 |
| 3.4 | 不存在的 tx hash | PASS | error code=-32001, message="transaction not found" |
| 3.5 | delegatecall 类型 trace | PASS | tx `0xd86f6e09...` (block 0x9a1eb0), callType="delegatecall" 正确返回, from/to 字段完整 |
| 3.6 | 深层调用链 (nested traceAddress) | PASS | 同一 tx 含 6 层调用深度, traceAddress 从 [] 到 [0,0,0,0,0], subtraces 层级正确 |
| 3.7 | create 类型 trace | PASS | tx `0x62dd2453...` (block 0x99b150), 内部 CREATE: type="create", createdAddr=0x28fc...f816, gasUsed=0xc07e18, init 含完整 bytecode |
| 3.8 | native value transfer (value>0) | **不适用** | Tempo 无 native gas token, 链上所有 trace 的 action.value 均为 0x0 |
| 3.9 | transactionPosition 正确性 | PASS | block 0x9a1eb0 含 4 笔 tx, transactionPosition 0→1→2→3 与 eth_getBlockByNumber 返回的 tx 顺序完全一致 |

---

## 4. 与官方 RPC 对比

| # | 测试项 | 结果 | 详情 |
|---|--------|------|------|
| 4.1 | eth_call 一致性 | **一致** | 同一区块同一请求, 返回值完全相同 |
| 4.2 | 区块数据一致性 | **一致** | hash/stateRoot/transactionsRoot/receiptsRoot/gasUsed 全部一致 |
| 4.3 | trace_transaction 单笔对比 | **一致** | 含普通 tx 和 AA tx (type=0x76), 与官方 RPC 完全相同 |
| 4.4 | trace_transaction 批量对比 (10 区块, 34 笔 tx) | **34/34 一致** | 所有 tx 的 trace 结果与官方 RPC 完全一致 |
| 4.5 | pre_traceMany vs trace_transaction 对比 | **一致** | 用链上 tx 参数 + 同一 block + tx 真实 gas_limit 调用 pre_traceMany, 对比 trace_transaction: 所有字段完全一致 (type/callType/from/to/value/gas/gasUsed/output/traceAddress/subtraces) |

---

---

## 5. 压力测试

### eth_multiCall 批量

| 请求数 | 耗时 | 错误数 | 结果 |
|--------|------|--------|------|
| 100 | 35ms | 0 | PASS |
| 500 | 47ms | 0 | PASS |
| 1000 | 40ms | 0 | PASS |
| 5000 | 131ms | 0 | PASS |

### pre_traceMany 批量

| 请求数 | 耗时 | 错误数 | 结果 |
|--------|------|--------|------|
| 100 | 38ms | 0 | PASS |
| 500 | 50ms | 0 | PASS |
| 5000 | 269ms | 0 | PASS |

### 并发测试

| 并发数 | 每请求笔数 | 平均响应 | HTTP 状态 | 结果 |
|--------|-----------|---------|-----------|------|
| 10 | 100 | ~4.5ms | 全部 200 | PASS |

**压测后节点状态**: 容器正常运行 (Up 45 minutes), 无 panic, 无 error, 出块跟随正常

---

## 补充说明

### Tempo 链特性导致的"不适用"项

以下测试项因 Tempo 链的架构特性无法测试, 属于链本身的设计而非节点功能缺陷:

- **native value transfer** (2.17, 3.8): Tempo 无传统 native gas token (gas 以 TIP-20 USD 稳定币支付), EVM 层禁止 value transfer, 返回 "value transfer not allowed"
- **insufficient funds for transfer** (2.20): 无 native token 余额, "余额不足转账"场景不存在。code=1001 路径已在 2.5 中通过 EVM 内 out of gas (Halt) 验证通过

### stateDiff 字段

API spec 中 pre_traceMany 返回值包含 `stateDiff` 字段, 但经确认: debankdefi/reth 未实现该字段, Go 节点虽返回但 DeBankCore 业务侧从未消费 (`chain/service.py` 只取 trace/logs/gasUsed/error)。`stateDiff` 属于世界状态层面的变更, 应由 `trace_debankBlock` / ETL 管道负责, 不属于预执行追踪的职责范围, 无需补充。

### AA tx 限制

AA tx (type=0x76) 的完整 AA 执行路径（多 calls 批量、fee payer、签名验证）无法通过 pre_traceMany 模拟, 因为 pre_traceMany 走的是普通 EVM call 路径。但 AA tx 的合约调用逻辑已通过提取链上真实 AA tx 的 from/to/data 进行了验证。

---

## 总结

- **DeBank 自定义 RPC 全部功能正常**: eth_multiCall 和 pre_traceMany 均按预期工作
- **与官方 RPC 数据完全一致**: eth_call、区块数据、trace_transaction (34 笔 tx) 全部一致, 无异常
- **节点同步正常**: snapshot 导入成功, follow 模式跟随链头
