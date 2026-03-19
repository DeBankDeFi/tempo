# Tempo 待办事项

## 高优先级

### 1. ECR repo 创建
- SRE 创建 `blockchain/tempo` repo（当前临时用 `blockchain/kava-x`）
- 创建后需更新：
  - `.github/workflows/build.debank.yml`: `IMAGE: blockchain/kava-x` → `IMAGE: blockchain/tempo`
  - `blockchain-misc-x3` compose.yml: 镜像地址
  - `docs/deployment.md`: 镜像地址（当前文档写的 `blockchain/tempo` 但实际不存在）
- 更新后重新构建并部署

### 2. Endpoint 注册
- 创建内部 DNS 记录：
  - `data.tempo.blockchain`
  - `pre.tempo.blockchain`
  - `trace.tempo.blockchain`
  - `archive.tempo.blockchain`

### 3. 生产部署
- 当前仅在 dev 机器 `blockchain-misc-x3` 上运行（端口 18545）
- 正式上线需部署到对应节点组（data/pre/trace/archive）
- 使用标准端口 8545

## 中优先级

### 4. 监控告警
- Prometheus metrics（节点已暴露 19001 端口）
- Grafana dashboard
- 飞书告警配置

### 5. 测试报告提交
- `docs/test-report.md` 最新更新未 commit（上次 commit 后又修改了 trace_transaction 对比等内容）

## 参考信息

- dev 机器: `blockchain-misc-x3`
- 容器端口映射: 18545:8545, 18546:8546, 40303:30303, 19001:9001
- EBS: vol-0e14b18861b31f2cc, 60G, tag chain:tempo, 挂载 /data/tempo
- 当前镜像: `blockchain/kava-x:amd64-6553257` (v1.4.3)
- 代码分支: `feature/debank_rpc` (已 push), `debank` (已同步)
