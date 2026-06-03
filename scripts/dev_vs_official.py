#!/usr/bin/env python3
"""
Dev (v1.7.0 d6e55f6) vs Official RPC byte-identical 多块对比。

每个块比对：
- eth_getBlockByNumber: hash / stateRoot / transactionsRoot / receiptsRoot
- 每笔 tx 的 receipt: status / gasUsed / blockHash / cumulativeGasUsed / contractAddress / logs.count
- 每笔 tx 的 trace_transaction: 全 JSON sha256（system tx null result 也对比 null vs null）

挑块策略：30 个 pre-T3 + 25 个 post-T3 + 5 个 head 临近 = 60 块。
"""
import json
import hashlib
import urllib.request
import sys
import time

RPC = "http://127.0.0.1:8566"
OFFICIAL = "https://rpc.tempo.xyz"

# 块矩阵：分 pre-T3 / post-T3 / near-head
PRE_T3 = list(range(10_080_000, 10_080_000 + 30 * 700, 700))     # 30 个 pre-T3 块，间隔 700
POST_T3 = list(range(17_100_000, 17_100_000 + 20 * 110_000, 110_000))  # 20 个 post-T3 跨越 17M-19M
POST_T4 = list(range(20_000_000, 20_000_000 + 15 * 220_000, 220_000))  # 15 个 post-T4 跨越 20M-23M
NEAR_HEAD = [23_300_000, 23_310_000, 23_320_000, 23_324_000, 23_325_000]  # 5 个 head 邻近 (post-T4)

ALL_BLOCKS = PRE_T3 + POST_T3 + POST_T4 + NEAR_HEAD


def call_rpc(url, method, params, timeout=20, retries=2):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=timeout)
            d = json.loads(resp.read())
            return d.get("result"), d.get("error")
        except Exception as e:
            last_err = e
            time.sleep(1.0 + attempt * 0.5)  # backoff
    return None, {"message": f"after {retries+1} attempts: {last_err}"}


def cmp_block(bn):
    """Compare a single block. Returns (passed_count, failed_count, fail_details)."""
    hb = hex(bn)
    passed = 0
    failed = 0
    fails = []

    # 1. Block header
    ldev, edev = call_rpc(RPC, "eth_getBlockByNumber", [hb, False])
    lof, eof = call_rpc(OFFICIAL, "eth_getBlockByNumber", [hb, False])
    if ldev is None or lof is None:
        fails.append(f"block fetch err dev={edev} off={eof}")
        return 0, 1, fails

    for f in ["hash", "stateRoot", "transactionsRoot", "receiptsRoot"]:
        if ldev.get(f) == lof.get(f):
            passed += 1
        else:
            failed += 1
            fails.append(f"{f}: dev={ldev.get(f)} off={lof.get(f)}")

    # 2. Each tx receipt + trace_transaction
    for txh in ldev.get("transactions", []):
        rdev, _ = call_rpc(RPC, "eth_getTransactionReceipt", [txh])
        rof, _ = call_rpc(OFFICIAL, "eth_getTransactionReceipt", [txh])
        if rdev is None or rof is None:
            failed += 1
            fails.append(f"receipt None tx={txh[:14]}")
            continue
        for f in ["status", "gasUsed", "blockHash", "cumulativeGasUsed", "contractAddress"]:
            if rdev.get(f) == rof.get(f):
                passed += 1
            else:
                failed += 1
                fails.append(f"receipt {f} tx={txh[:14]}: dev={rdev.get(f)} off={rof.get(f)}")
        # logs count match
        if len(rdev.get("logs", [])) == len(rof.get("logs", [])):
            passed += 1
        else:
            failed += 1
            fails.append(f"receipt logs count tx={txh[:14]}: dev={len(rdev.get('logs',[]))} off={len(rof.get('logs',[]))}")

        # trace_transaction sha256
        tdev, _ = call_rpc(RPC, "trace_transaction", [txh])
        tof, _ = call_rpc(OFFICIAL, "trace_transaction", [txh])
        # null result also compared
        sha_dev = hashlib.sha256(json.dumps(tdev, sort_keys=True).encode()).hexdigest()
        sha_of = hashlib.sha256(json.dumps(tof, sort_keys=True).encode()).hexdigest()
        if sha_dev == sha_of:
            passed += 1
        else:
            failed += 1
            fails.append(f"trace_transaction tx={txh[:14]}: dev_sha={sha_dev[:16]} off_sha={sha_of[:16]}")

    return passed, failed, fails


def main():
    print(f"Dev vs Official byte-identical comparison")
    print(f"Total blocks: {len(ALL_BLOCKS)}")
    print(f"  pre-T3:  {len(PRE_T3)}")
    print(f"  post-T3: {len(POST_T3)}")
    print(f"  near-head: {len(NEAR_HEAD)}")
    print()

    total_pass = 0
    total_fail = 0
    block_fail_count = 0
    sample_fails = []

    start = time.time()
    for i, bn in enumerate(ALL_BLOCKS):
        p, f, fails = cmp_block(bn)
        total_pass += p
        total_fail += f
        if f > 0:
            block_fail_count += 1
            for d in fails[:2]:
                sample_fails.append(f"  block {bn}: {d}")
        # Progress every 10 blocks
        if (i + 1) % 10 == 0:
            elapsed = time.time() - start
            print(f"  [{i+1}/{len(ALL_BLOCKS)}] {elapsed:.0f}s elapsed; pass={total_pass} fail={total_fail}")

    print()
    print("=" * 50)
    print(f"Total blocks:       {len(ALL_BLOCKS)}")
    print(f"Blocks with fail:   {block_fail_count}")
    print(f"Per-field PASS:     {total_pass}")
    print(f"Per-field FAIL:     {total_fail}")
    print(f"Time:               {time.time()-start:.0f}s")

    if sample_fails:
        print()
        print("Fail samples (first 20):")
        for s in sample_fails[:20]:
            print(s)

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
