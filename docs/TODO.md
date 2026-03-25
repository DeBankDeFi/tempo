# Tempo 待办事项

## 已完成

- ~~ECR repo 创建~~ → `blockchain/tempo` 已创建，CI 已更新
- ~~Endpoint 注册~~ → data/pre/trace/archive.tempo.blockchain 全部可用
- ~~生产部署~~ → 2 台机器（172.22.141.54: data+pre, 172.22.179.114: trace+archive），镜像 v1.4.3

## 待办

### 1. 监控告警
- Prometheus metrics（节点已暴露 9001 端口）
- Grafana dashboard
- 飞书告警配置

### 2. pre_traceMany fee log 改造
- 当前 pre_traceMany 缺少 Tempo handler 层产生的 TIP-20 fee log（普通 tx 少 1 条，AA tx 少 2~3 条）
- 改造方案：EVM 执行后根据 gasUsed + basefee 计算 fee，读链上 fee token 偏好，追加 Transfer log
- 前置依赖：DeBankCore `engine.py` 中 Tempo 需加入 gasPrice 配置列表（当前硬编码为 0x0）
- 详见 `docs/test-report.md` 中"pre_traceMany 缺少 TIP20 fee 相关 log"章节

### 3. trace_debankBlock 上线

- [ ] background-tracer dry-run 验证（上线阻塞项，需 binary 部署到 dev 机器）
- [ ] 合并 PR #4 (`feature/debank_rpc` → `debank`)
- [ ] 生产部署（2 台机器更新镜像）
- [ ] 部署 background-tracer sidecar（Kafka/S3 + chain_id=4217）

### 4. 多 call AA tx 适配

- Tempo 0x76 tx 支持 `calls: Vec<Call>` 多调用原子执行
- 当前 `DebankTransaction.to/input/value` 只展示第一个 call，其余 call 信息仅在 traces 中
- **链上已存在多 call AA tx**（如 block 0x9eeb98: approve + swap 双 call）
- 实际表现：`txs` 中 `to=null, input=第一个call`，第二个 call 目标/数据仅在 traces `trace_address=[1]` 可见
- 需评估 DeBankCore 是否仅消费 traces（则无影响）还是依赖 txs.to/input（则需适配）

### 5. dev 机器清理
- blockchain-misc-x3 上的 tempo 容器已停止，EBS 已 detach（snapshot: snap-08859f84cfb8b1611）
- 确认不再需要后可删除 volume vol-0e14b18861b31f2cc 和 snapshot

## 参考信息

- 代码分支: `feature/debank_rpc` / `debank`
- ECR: `294354037686.dkr.ecr.ap-northeast-1.amazonaws.com/blockchain/tempo:v1.4.3`
- Release: https://github.com/DeBankDeFi/tempo/releases/tag/v1.4.3
- 线上节点: data/pre/trace/archive.tempo.blockchain
