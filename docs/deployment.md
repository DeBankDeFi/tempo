# Tempo

## ToC

| Key | Value |
|-----|-------|
| Name | Tempo |
| EVM 兼容性 | ✅ |
| 客户端实现语言 | Rust |
| 官方 Code Repo | https://github.com/tempoxyz/tempo |
| DeBank Code Repo | https://github.com/DeBankDeFi/tempo |
| 官方 RPC Endpoint | https://rpc.tempo.xyz |
| 开发者文档 | https://docs.tempo.xyz |
| 部署文档 | 本文档 |
| Chain ID | 4217 (mainnet / presto) |
| 浏览器 | https://explorer.tempo.xyz |
| Token | 无原生代币（gas 以 USDC/USDT 支付） |
| Featured APIs | All |

## Networks

| Network | Chain ID | --chain 参数 | Follow URL |
|---------|----------|-------------|------------|
| Presto (mainnet) | 4217 | `mainnet` | wss://rpc.presto.tempo.xyz |
| Moderato | 42431 | `moderato` | wss://rpc.moderato.tempo.xyz |
| Andantino (testnet) | 42429 | `testnet` | wss://rpc.testnet.tempo.xyz |
| Dev | 1337 | `dev` | - |

## Endpoints

| RPC Endpoint | Type | Comment | Ready |
|-------------|------|---------|-------|
| data.tempo.blockchain | state(data) | 数据节点组 | |
| pre.tempo.blockchain | Pre exec | 预执行节点组 | |
| trace.tempo.blockchain | Trace | Trace 节点组 | |
| archive.tempo.blockchain | Archive | Archive 节点组 | |

## Deployment

Tempo 是单体架构，共识层和执行层集成在同一个二进制中，只需部署 1 个 service。

DeBank 节点使用 **follow 模式**运行（跳过共识，通过 WebSocket 跟随官方节点同步），无需 validator key。

### Snapshot

Tempo 官方提供 snapshot 下载:
- Mainnet: `https://snapshots.tempoxyz.dev/4217`
- Moderato: `https://snapshots.tempoxyz.dev/42431`
- Andantino: `https://snapshots.tempoxyz.dev/42429`

下载方式:
```bash
# 在容器内或二进制直接执行
tempo download --chain mainnet
```

### compose.yml

```yaml
version: "3.5"

services:
  tempo:
    container_name: tempo
    restart: unless-stopped
    stop_signal: SIGTERM
    stop_grace_period: 300s
    image: 294354037686.dkr.ecr.ap-northeast-1.amazonaws.com/blockchain/tempo:<TAG>
    ports:
      - 8545:8545
      - 8546:8546
      - 30303:30303
      - 30303:30303/udp
      - 9001:9001
    volumes:
      - /tempo:/data
    deploy:
      resources:
        limits:
          cpus: "8"
          memory: "32G"
    command:
      - node
      - --chain=mainnet
      - --datadir=/data
      - --follow=auto
      - --log.stdout.filter=info
      - --http
      - --http.addr=0.0.0.0
      - --http.port=8545
      - --http.api=all
      - --ws
      - --ws.addr=0.0.0.0
      - --ws.port=8546
      - --ws.api=all
      - --port=30303
      - --discovery.port=30303
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--chain=mainnet` | 网络选择: `mainnet` / `moderato` / `testnet` |
| `--follow=auto` | Follow 模式，自动使用对应网络的官方 WebSocket endpoint 同步。也可指定自定义 URL: `--follow=wss://your-endpoint` |
| `--datadir=/data` | 数据目录 |
| `--http.api=all` | 开放所有 RPC namespace（含 DeBank 自定义的 `pre_traceMany` 和 `eth_multiCall`） |
| `--log.stdout.filter=info` | 日志级别 |

### 端口

| 端口 | 用途 |
|------|------|
| 8545 | HTTP RPC |
| 8546 | WebSocket RPC |
| 30303 | Execution P2P (TCP + UDP) |
| 9001 | Metrics (Prometheus) |

### 部署步骤

```bash
# 1. 创建数据目录
sudo mkdir -p /tempo
sudo mkdir -p /opt/apps/tempo

# 2. 将 compose.yml 放到 /opt/apps/tempo/
# 3. 登录 ECR
aws ecr get-login-password --region ap-northeast-1 | sudo docker login --username AWS --password-stdin 294354037686.dkr.ecr.ap-northeast-1.amazonaws.com

# 4. 启动
cd /opt/apps/tempo && sudo docker compose up -d

# 5. 查看日志
sudo docker compose logs --since 5m tempo

# 6. 检查同步状态
curl -s -X POST http://localhost:8545 \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"eth_syncing","params":[],"id":1}' | jq

# 7. 验证 DeBank RPC
# eth_multiCall
curl -s -X POST http://localhost:8545 \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"eth_multiCall","params":[[{"to":"0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE","data":"0x18160ddd"}]],"id":1}' | jq

# pre_traceMany
curl -s -X POST http://localhost:8545 \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"pre_traceMany","params":[[]],"id":1}' | jq
```

### 注意事项

1. **无共识组件**: 与 Telos 不同，Tempo 是单体架构，不需要额外部署 nodeos / consensus-client 等组件
2. **Follow 模式**: DeBank 节点使用 `--follow=auto` 模式，跟随官方节点同步，不参与出块
3. **无原生代币**: Tempo 没有传统意义的 native gas token，gas 以 USDC/USDT 支付。`0xEeee...eEeE` 的 `balanceOf` 返回 native balance（可能为 0）
4. **Snapshot**: 首次部署建议先下载 snapshot 加速同步，使用 `tempo download --chain mainnet` 命令
5. **ECR 镜像**: 需要先在 ECR 创建 `blockchain-tempo` repository
