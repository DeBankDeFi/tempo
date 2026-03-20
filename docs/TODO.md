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

### 3. dev 机器清理
- blockchain-misc-x3 上的 tempo 容器已停止，EBS 已 detach（snapshot: snap-08859f84cfb8b1611）
- 确认不再需要后可删除 volume vol-0e14b18861b31f2cc 和 snapshot

## 参考信息

- 代码分支: `feature/debank_rpc` / `debank`
- ECR: `294354037686.dkr.ecr.ap-northeast-1.amazonaws.com/blockchain/tempo:v1.4.3`
- Release: https://github.com/DeBankDeFi/tempo/releases/tag/v1.4.3
- 线上节点: data/pre/trace/archive.tempo.blockchain
