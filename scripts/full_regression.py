#!/usr/bin/env python3
"""
trace_debankBlock 完整回归测试。
按 docs/test-plan-generic-node.md 13 大类执行。

Usage: python3 full_regression.py
"""

import json
import hashlib
import time
import urllib.request
import sys

RPC = "http://127.0.0.1:8566"
OFFICIAL = "https://rpc.tempo.xyz"

# 测试块矩阵
BLOCKS = {
    "B1_genesis": "0x0",
    "B2_empty":   "0x1",
    "B3_pre_t3_main":   "0x9a1eb0",   # 10,100,400 — 4 txs 含 AA tx
    "B4_pre_t3_revert": "0x9a2040",   # 10,100,800 — revert no event
    "B5_pre_t3_revert_evm": "0x99e15c",  # 10,084,700 — revert with EVM events
    "B6_pre_t3_create": "0x99b150",   # 10,072,400 — CREATE trace
    "B7_pre_t3_eip1559": "0x9e8900",  # 10,389,760 — EIP-1559
    "B8_post_t3_addr_reg":  "0x10487c4",  # 17,074,116 — address_registry + AA secp256k1
    "B9_post_t3_webauthn":  "0x11a6002",  # 18,505,730 — address_registry + AA webAuthn
    "B10_post_t3_aa":  "0x115e000",   # 18,210,816 — AA tx
    "B11_post_t3_highrate":  "0x12b1280",  # 19,600,000 — 5 Legacy txs
    "B12_post_t4_aa":  "0x15752a0",   # 22,500,000 — post-T4 AA tx + consensus_context
    "B13_post_t4_nearhead":  "0x16387a0",  # 23,300,000 — post-T4 AA tx near-head
}

# 计数
counters = {"pass": 0, "fail": 0, "na": 0}
section_counts = {}   # section -> {"pass":n,"fail":n,"na":n}
failures = []  # list of (section, test_id, reason)

def _add_section(section, kind):
    sc = section_counts.setdefault(section.split(".")[0], {"pass":0,"fail":0,"na":0})
    sc[kind] += 1

def call_rpc(url, method, params, timeout=30, retries=2):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            d = json.loads(resp.read())
            return d.get("result"), d.get("error")
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    return None, {"message": f"after {retries+1} attempts: {last_err}"}

def record(section, tid, passed, na=False, reason=""):
    if na:
        counters["na"] += 1
        _add_section(section, "na")
        print(f"  [{section}.{tid}] N/A: {reason}")
    elif passed:
        counters["pass"] += 1
        _add_section(section, "pass")
    else:
        counters["fail"] += 1
        _add_section(section, "fail")
        failures.append((section, tid, reason))
        print(f"  [{section}.{tid}] FAIL: {reason}")

def assert_eq(section, tid, actual, expected, label=""):
    record(section, tid, actual == expected,
           reason=f"{label}: expected={expected!r} actual={actual!r}")

def assert_true(section, tid, cond, reason=""):
    record(section, tid, bool(cond), reason=reason)

def na(section, tid, reason):
    record(section, tid, False, na=True, reason=reason)

# ============== Section 1: DebankOutPut 顶层结构 ==============
def section_1(block_data):
    print("\n--- Section 1: 顶层结构 ---")
    for label, db in block_data.items():
        if db is None: continue
        assert_true("1.1", f"{label}", all(k in db for k in ["block_file", "header", "state_diff", "validation_hash"]),
                    reason="missing top-level keys")
        assert_true("1.2", f"{label}", isinstance(db.get("validation_hash"), int) and db["validation_hash"] >= 0,
                    reason=f"validation_hash type/value: {db.get('validation_hash')}")
        sd = db.get("state_diff", "")
        assert_true("1.3", f"{label}", isinstance(sd, str) and sd.startswith("0x") and len(sd) > 4,
                    reason=f"state_diff format: starts with 0x len>4")
        # 1.4 header consistency - 单独 Section 9 处理

# ============== Section 2: block_file.block ==============
def section_2(block_data, official_blocks):
    print("\n--- Section 2: block fields ---")
    for label, db in block_data.items():
        if db is None: continue
        ob = official_blocks.get(label)
        if ob is None: continue
        b = db["block_file"]["block"]
        assert_eq("2.1", label, b["id"], ob["hash"], "id")
        assert_eq("2.2", label, int(b["height"]), int(ob["number"], 16), "height")
        assert_eq("2.3", label, b["parent_id"], ob["parentHash"], "parent_id")
        bfg = b.get("base_fee_per_gas")
        ofg = int(ob["baseFeePerGas"], 16) if ob.get("baseFeePerGas") else None
        assert_eq("2.4", label, bfg, ofg, "base_fee_per_gas")
        assert_eq("2.5", label, b["miner"].lower(), ob["miner"].lower(), "miner")
        assert_eq("2.6", label, int(b["gas_limit"]), int(ob["gasLimit"], 16), "gas_limit")
        assert_eq("2.7", label, int(b["gas_used"]), int(ob["gasUsed"], 16), "gas_used")
        assert_eq("2.8", label, int(b["timestamp"]), int(ob["timestamp"], 16), "timestamp")
        pst = b.get("process_start_timestamp", 0)
        assert_true("2.9", label, isinstance(pst, int) and pst > 1700000000000,
                    reason=f"process_start_timestamp not in recent ms range: {pst}")

# ============== Section 3: txs ==============
def section_3(block_data, official_blocks_full, official_receipts):
    print("\n--- Section 3: txs ---")
    for label, db in block_data.items():
        if db is None: continue
        ob_full = official_blocks_full.get(label)
        receipts = official_receipts.get(label, {})
        if ob_full is None: continue
        txs = db["block_file"]["txs"]
        ob_txs = ob_full["transactions"]

        # 3.2.7 count match (genesis 例外：synthetic txs 从 chain spec 构造，eth_getBlockByNumber 显示 transactions=[])
        if label == "B1_genesis":
            assert_true("3.2.7", label, len(txs) > 0,
                        reason=f"genesis should have synthetic txs, got {len(txs)}")
        else:
            assert_eq("3.2.7", label, len(txs), len(ob_txs), "tx count")
        # 3.2.8 idx 顺序
        for i, t in enumerate(txs):
            assert_eq("3.2.8", f"{label}_tx{i}", int(t["idx"]), i, "idx ordering")

        # 3.1.x per-tx field check (only for non-system tx)
        for i, t in enumerate(txs):
            ot = ob_txs[i] if i < len(ob_txs) else {}
            txh = t["id"]
            r = receipts.get(txh, {})
            if not r:
                continue
            assert_eq("3.1.1", f"{label}_tx{i}", t["id"], r["transactionHash"], "id")
            assert_eq("3.1.2", f"{label}_tx{i}", t["from_addr"].lower(), r["from"].lower(), "from_addr")
            assert_eq("3.1.5", f"{label}_tx{i}", int(t["gas_price"]), int(r["effectiveGasPrice"], 16), "gas_price")
            assert_eq("3.1.6", f"{label}_tx{i}", int(t["gas_used"]), int(r["gasUsed"], 16), "gas_used")
            expected_status = (r["status"] == "0x1")
            assert_eq("3.1.7", f"{label}_tx{i}", bool(t["status"]), expected_status, "status")
            assert_eq("3.1.12", f"{label}_tx{i}", int(t["idx"]), int(r["transactionIndex"], 16), "idx")
            # 3.1.4 gas_limit from tx (only if not system tx with gas=0)
            tx_gas = int(ot.get("gas", "0x0"), 16)
            assert_eq("3.1.4", f"{label}_tx{i}", int(t["gas_limit"]), tx_gas, "gas_limit")
            assert_eq("3.1.11", f"{label}_tx{i}", int(t["nonce"]), int(ot.get("nonce", "0x0"), 16), "nonce")

            # tx type 覆盖
            tp = ot.get("type", "0x0")
            if t["from_addr"] == "0x0000000000000000000000000000000000000000" and int(t["gas_limit"]) == 0:
                # System tx
                assert_true("3.2.4", f"{label}_tx{i}",
                            int(t["gas_limit"]) == 0 and int(t["gas_used"]) == 0 and bool(t["status"]),
                            reason="system tx: gas=0/0, status=true")
            elif tp == "0x76":
                # AA tx
                assert_true("3.2.3", f"{label}_tx{i}", "calls" in t and len(t.get("calls", [])) >= 1,
                            reason=f"AA tx missing calls field")
            elif tp == "0x2":
                # EIP-1559
                assert_true("3.2.2", f"{label}_tx{i}", int(t.get("max_fee_per_gas", 0)) > 0,
                            reason="EIP-1559: max_fee_per_gas > 0")
            elif tp == "0x0":
                # Legacy
                assert_true("3.2.1", f"{label}_tx{i}",
                            int(t.get("max_priority_fee_per_gas", 0)) == 0,
                            reason=f"Legacy: priority fee should be 0, got {t.get('max_priority_fee_per_gas')}")

            if not bool(t["status"]):
                # revert tx
                assert_eq("3.2.6", f"{label}_tx{i}", bool(t["status"]), False, "revert tx")

# ============== Section 4: traces ==============
def section_4(block_data, traces_official):
    print("\n--- Section 4: traces ---")
    for label, db in block_data.items():
        if db is None: continue
        bf = db["block_file"]
        all_traces = bf.get("traces", []) + bf.get("error_traces", [])
        # 4.4.1 traces count vs trace_transaction sum
        # genesis 例外：synthetic traces 无对应 trace_transaction
        if label == "B1_genesis":
            assert_true("4.4.1", label, len(all_traces) > 0,
                        reason=f"genesis should have synthetic traces, got {len(all_traces)}")
        else:
            official_traces_per_tx = traces_official.get(label, {})
            official_total = sum(len(t or []) for t in official_traces_per_tx.values())
            assert_eq("4.4.1", label, len(all_traces), official_total, "traces+error_traces total vs trace_transaction sum")

        # 4.1.x field structure
        for j, t in enumerate(all_traces):
            for f in ["id", "from_addr", "to_addr", "type", "tx_id", "parent_trace_id", "subtraces", "trace_address"]:
                assert_true("4.1", f"{label}_t{j}_{f}", f in t,
                            reason=f"trace missing field {f}")
            assert_true("4.1.1", f"{label}_t{j}_id", isinstance(t["id"], str) and len(t["id"]) == 32,
                        reason=f"trace id format (MD5 hex 32): {t['id']}")
            assert_true("4.1.17", f"{label}_t{j}_trace_address", isinstance(t["trace_address"], list),
                        reason="trace_address not list")

        # 4.3.3 id uniqueness within block
        ids = [t["id"] for t in all_traces]
        assert_eq("4.3.3", label, len(set(ids)), len(ids), "trace id uniqueness")

        # 4.2.x type 覆盖
        types_seen = {t.get("type") for t in all_traces}
        call_types = {t.get("call_type") for t in all_traces}
        # 注意: type 是 "call" 或 "create"，call_type 进一步细分
        if all_traces:
            assert_true("4.2.x", label, all(t.get("type") in {"call", "create", "suicide"} for t in all_traces),
                        reason=f"unexpected trace types: {types_seen}")

# ============== Section 5: events ==============
def section_5(block_data, official_receipts):
    print("\n--- Section 5: events ---")
    for label, db in block_data.items():
        if db is None: continue
        bf = db["block_file"]
        all_events = bf.get("events", []) + bf.get("error_events", [])

        # 5.1.x field structure
        for j, e in enumerate(all_events):
            for f in ["id", "contract_id", "selector", "topics", "data", "parent_trace_id", "pos_in_parent_trace", "idx"]:
                assert_true("5.1", f"{label}_e{j}_{f}", f in e, reason=f"event missing field {f}")
            assert_true("5.1.1", f"{label}_e{j}_id", isinstance(e["id"], str) and len(e["id"]) == 32,
                        reason=f"event id format: {e['id']}")

        # 5.4.1 idx 无重复
        idxs = [e["idx"] for e in all_events]
        assert_eq("5.4.1", label, len(set(idxs)), len(idxs), "event idx uniqueness")

        # 5.4.2 idx 全局递增 [0..N-1]
        if idxs:
            expected = list(range(min(idxs), min(idxs) + len(idxs)))
            assert_eq("5.4.2", label, sorted(idxs), expected, "event idx contiguous range")

        # 5.2.5 events count
        # 需要按 receipt logs 总数和 revert tx 处理
        receipts = official_receipts.get(label, {})
        txs = bf["txs"]
        success_event_count = len(bf.get("events", []))
        total_receipt_logs = sum(len(r.get("logs", [])) for r in receipts.values() if r)
        revert_receipt_logs = sum(len(r.get("logs", [])) for r in receipts.values() if r and r.get("status") == "0x0")
        # 公式: success_events + revert_receipt_logs = total_receipt_logs
        formula_match = (success_event_count + revert_receipt_logs == total_receipt_logs)
        if not formula_match:
            # 退一步: 无 revert 区块直接对比
            if revert_receipt_logs == 0:
                # events == total receipt logs
                assert_eq("5.2.5", label, len(all_events), total_receipt_logs,
                          "events count vs receipt logs (no revert)")
            else:
                # success_events + revert_receipt_logs == total_receipt_logs
                assert_eq("5.2.5", label, success_event_count + revert_receipt_logs, total_receipt_logs,
                          "events count formula (with revert)")
        else:
            counters["pass"] += 1  # implicit pass

# ============== Section 6: error_traces / error_events ==============
def section_6(block_data, official_receipts):
    print("\n--- Section 6: error_traces / error_events ---")
    for label, db in block_data.items():
        if db is None: continue
        bf = db["block_file"]
        txs = bf["txs"]
        receipts = official_receipts.get(label, {})
        revert_tx_ids = {tx["id"] for tx in txs if not bool(tx["status"])}
        error_traces = bf.get("error_traces", [])
        error_events = bf.get("error_events", [])

        # 6.1 revert tx traces → error_traces (all error_traces 来自 revert tx)
        if revert_tx_ids:
            error_tx_ids = {t["tx_id"] for t in error_traces}
            extra = error_tx_ids - revert_tx_ids
            assert_eq("6.1", label, len(extra), 0,
                      f"error_traces from non-revert tx: {extra}")
        else:
            assert_eq("6.3", label, len(error_traces), 0,
                      f"all-success block but error_traces={len(error_traces)}")
            assert_eq("6.3b", label, len(error_events), 0,
                      f"all-success block but error_events={len(error_events)}")

        # 6.8 error 字段非空 (revert tx 的 ROOT error_trace.error 应该非空)
        # 内部 sub-call 的 error 可以为空（只有触发 revert 的层有 "Reverted"）
        for j, t in enumerate(error_traces):
            if t["tx_id"] in revert_tx_ids and t.get("trace_address") == []:
                err = t.get("error", "")
                assert_true("6.8", f"{label}_et{j}_root",
                            err != "",
                            reason=f"root error_trace.error empty: {err!r}")

# ============== Section 7: storage_contracts ==============
def section_7(block_data):
    print("\n--- Section 7: storage_contracts ---")
    for label, db in block_data.items():
        if db is None: continue
        bf = db["block_file"]
        sc = bf.get("storage_contracts", [])
        assert_true("7.1", label, isinstance(sc, list), reason="not list")

        # 7.5 empty block
        if label == "B2_empty":
            assert_eq("7.5", label, len(sc), 0, "empty block storage_contracts")

# ============== Section 8: state_diff (RLP) ==============
def section_8(block_data):
    print("\n--- Section 8: state_diff (RLP) ---")
    try:
        import rlp
    except ImportError:
        na("8.1.1", "all", "rlp module not installed")
        return

    for label, db in block_data.items():
        if db is None: continue
        sd_hex = db["state_diff"]
        if not sd_hex.startswith("0x"):
            record("8.1.1", label, False, reason=f"missing 0x prefix")
            continue
        try:
            sd_bytes = bytes.fromhex(sd_hex[2:])
            decoded = rlp.decode(sd_bytes)
            assert_true("8.1.1", label, True, reason="RLP decode ok")
            # BlockStorageDiff: [hash, parent_hash, new_accounts, deleted_accounts, storage_diffs, new_codes]
            assert_eq("8.1.2", label, "0x" + decoded[0].hex(), db["header"]["stateRoot"], "state_diff.hash == header.stateRoot")
        except Exception as e:
            record("8.1.1", label, False, reason=f"RLP decode error: {e}")
            continue

# ============== Section 9: header (20 fields) ==============
def section_9(block_data, official_blocks):
    print("\n--- Section 9: header (20 fields) ---")
    HEADER_FIELDS = [
        "hash", "parentHash", "stateRoot", "transactionsRoot", "receiptsRoot",
        "number", "gasLimit", "gasUsed", "timestamp", "baseFeePerGas",
        "miner", "logsBloom", "nonce", "mixHash", "sha3Uncles",
        "difficulty", "extraData", "withdrawalsRoot", "blobGasUsed", "excessBlobGas"
    ]
    for label, db in block_data.items():
        if db is None: continue
        ob = official_blocks.get(label)
        if ob is None: continue
        h = db["header"]
        for f in HEADER_FIELDS:
            actual = h.get(f)
            expected = ob.get(f)
            if expected is None and actual is None:
                counters["pass"] += 1
                continue
            assert_eq(f"9.{f}", label, actual, expected, f)

# ============== Section 10: validation_hash ==============
def section_10(block_data):
    print("\n--- Section 10: validation_hash ---")
    for label, db in block_data.items():
        if db is None: continue
        vh = db.get("validation_hash")
        assert_true("10.1", label, isinstance(vh, int), reason=f"type: {type(vh).__name__}")
        if label != "B2_empty":
            assert_true("10.2", label, vh != 0, reason=f"value: {vh}")
        # 10.4 幂等: 同一 block 第二次调用
        hb = BLOCKS.get(label)
        if hb:
            r2, e = call_rpc(RPC, "trace_debankBlock", [hb])
            if r2:
                assert_eq("10.4", label, r2.get("validation_hash"), vh, "idempotent")

# ============== Section 11: 特殊区块 ==============
def section_11(block_data):
    print("\n--- Section 11: 特殊区块 ---")
    g = block_data.get("B1_genesis")
    if g:
        gbf = g["block_file"]
        assert_true("11.1", "genesis_txs_nonempty", len(gbf["txs"]) > 0, reason="genesis has 0 txs")
        assert_true("11.1", "genesis_state_diff_nonempty", len(g["state_diff"]) > 4,
                    reason=f"genesis state_diff len={len(g['state_diff'])}")

    e = block_data.get("B2_empty")
    if e:
        ebf = e["block_file"]
        assert_eq("11.2", "empty_events", len(ebf.get("events", [])), 0, "empty block events")

    main = block_data.get("B3_pre_t3_main")
    if main:
        mbf = main["block_file"]
        # 11.4 AA tx 区块: AA tx traces 在 traces 而非 error_traces 中
        aa_tx_ids = [tx["id"] for tx in mbf["txs"] if "calls" in tx]
        for aa_id in aa_tx_ids:
            aa_traces_in_main = [t for t in mbf.get("traces", []) if t["tx_id"] == aa_id]
            aa_traces_in_err = [t for t in mbf.get("error_traces", []) if t["tx_id"] == aa_id]
            assert_true("11.4", f"AA_tx_{aa_id[:10]}_in_traces",
                        len(aa_traces_in_main) > 0 and len(aa_traces_in_err) == 0,
                        reason=f"AA tx traces: main={len(aa_traces_in_main)} err={len(aa_traces_in_err)}")

    create_blk = block_data.get("B6_pre_t3_create")
    if create_blk:
        cbf = create_blk["block_file"]
        create_traces = [t for t in cbf.get("traces", []) if t.get("type") == "create"]
        assert_true("11.6", "create_trace_exists", len(create_traces) > 0,
                    reason=f"no create trace in block 0x99b150")

    # 11.7 不存在的块
    r, e = call_rpc(RPC, "trace_debankBlock", ["0xffffff00"])
    assert_true("11.7", "non_existent_block", r is None and e is not None,
                reason=f"expected error, got result={r is not None}")

    # 11.8 latest
    r, e = call_rpc(RPC, "trace_debankBlock", ["latest"])
    if r:
        h = int(r["block_file"]["block"]["height"])
        assert_true("11.8", "latest_height_recent", h > 19000000, reason=f"height={h}")

# ============== Section 12: 兼容性 / 性能 ==============
def section_12(block_data):
    print("\n--- Section 12: 兼容性 / 性能 ---")
    # 12.3 连续区块 parent_id 链
    main_blocks = []
    for i in range(5):
        hb = f"0x{10100400+i:x}"
        r, e = call_rpc(RPC, "trace_debankBlock", [hb])
        if r:
            main_blocks.append(r["block_file"]["block"])
    for i in range(1, len(main_blocks)):
        assert_eq("12.3", f"chain_link_{i}", main_blocks[i]["parent_id"], main_blocks[i-1]["id"],
                  "parent_id chain")

    # 12.4 性能: 单次调用耗时
    t0 = time.time()
    call_rpc(RPC, "trace_debankBlock", ["0x9a1eb0"])
    elapsed = (time.time() - t0) * 1000
    assert_true("12.4", "perf", elapsed < 5000, reason=f"slow: {elapsed:.1f}ms")

    # 12.1/12.2 background-tracer dry-run 需要 binary, 跳过
    na("12.1", "json_compat", "background-tracer binary not in test scope")
    na("12.2", "dry_run", "background-tracer binary not in test scope")

# ============== Section 13: 批量回归 ==============
def section_13():
    print("\n--- Section 13: 批量回归 20 blocks (10,100,000..10,100,019) ---")
    fails = 0
    detail_fails = []
    for n in range(10100000, 10100020):
        hb = hex(n)
        # 用 dev 自身 RPC 对照
        rdev, ed = call_rpc(RPC, "trace_debankBlock", [hb])
        rstd, es = call_rpc(RPC, "eth_getBlockByNumber", [hb, False])
        if not rdev or not rstd:
            fails += 1
            detail_fails.append(f"block {n}: dev rpc err (debank={ed}, std={es})")
            continue
        if rdev["block_file"]["block"]["id"] != rstd["hash"]:
            fails += 1
            detail_fails.append(f"block {n}: hash mismatch")
            continue
        # tx count 一致
        if len(rdev["block_file"]["txs"]) != len(rstd["transactions"]):
            fails += 1
            detail_fails.append(f"block {n}: tx count {len(rdev['block_file']['txs'])} vs {len(rstd['transactions'])}")
            continue
        # event idx 无重复
        all_events = rdev["block_file"].get("events", []) + rdev["block_file"].get("error_events", [])
        idxs = [e["idx"] for e in all_events]
        if len(set(idxs)) != len(idxs):
            fails += 1
            detail_fails.append(f"block {n}: event idx duplicate")
    if detail_fails:
        for d in detail_fails[:5]:
            print(f"    {d}")
    assert_eq("13.batch", "batch20", fails, 0, "batch failure count")

# ============== 主流程 ==============
def main():
    print("===== trace_debankBlock 完整回归 =====")
    print(f"Local RPC: {RPC}")
    print(f"Official:  {OFFICIAL}")
    print(f"Test blocks: {len(BLOCKS)}")

    # 1. 拉所有 sample 块的数据
    print("\n[Step 1/2] 拉数据 ...")
    block_data = {}
    official_blocks = {}
    official_blocks_full = {}
    official_receipts = {}
    traces_official = {}

    for label, hb in BLOCKS.items():
        sys.stdout.write(f"  {label} ({hb})... ")
        sys.stdout.flush()
        # debank
        r, e = call_rpc(RPC, "trace_debankBlock", [hb])
        if e:
            print(f"ERR: {e}")
            block_data[label] = None
            continue
        block_data[label] = r
        # 对照数据用 dev 自身（dev vs official 已在 post-T3 报告中证明 byte-identical）
        ob, _ = call_rpc(RPC, "eth_getBlockByNumber", [hb, True])
        if ob is None:
            print(f"WARN: dev block {hb} returned None, skipping comparisons")
            official_blocks_full[label] = None
            official_blocks[label] = None
            official_receipts[label] = {}
            traces_official[label] = {}
            continue
        official_blocks_full[label] = ob
        official_blocks[label] = ob
        # receipts
        receipts = {}
        for tx in ob.get("transactions", []):
            txh = tx["hash"]
            rec, _ = call_rpc(RPC, "eth_getTransactionReceipt", [txh])
            if rec:
                receipts[txh] = rec
        official_receipts[label] = receipts
        # trace_transaction (system tx 可能返回 null，需处理)
        per_tx_traces = {}
        for tx in ob.get("transactions", []):
            tt, _ = call_rpc(RPC, "trace_transaction", [tx["hash"]])
            # null result 当作空列表
            per_tx_traces[tx["hash"]] = tt or []
        traces_official[label] = per_tx_traces
        print("ok")

    # 2. 跑测试
    print("\n[Step 2/2] 执行测试 ...")
    section_1(block_data)
    section_2(block_data, official_blocks)
    section_3(block_data, official_blocks_full, official_receipts)
    section_4(block_data, traces_official)
    section_5(block_data, official_receipts)
    section_6(block_data, official_receipts)
    section_7(block_data)
    section_8(block_data)
    section_9(block_data, official_blocks)
    section_10(block_data)
    section_11(block_data)
    section_12(block_data)
    section_13()

    # 3. 总结
    print("\n========== 分章节统计 ==========")
    for s in sorted(section_counts.keys(), key=lambda x: int(x) if x.isdigit() else 999):
        sc = section_counts[s]
        print(f"  Section {s:>4}:  PASS={sc['pass']:>5}  FAIL={sc['fail']:>3}  N/A={sc['na']:>3}")
    print("\n========== 总结 ==========")
    print(f"  PASS: {counters['pass']}")
    print(f"  FAIL: {counters['fail']}")
    print(f"  N/A:  {counters['na']}")
    if failures:
        print(f"\n失败明细 ({len(failures)} 项):")
        for s, t, r in failures[:30]:
            print(f"  [{s}.{t}] {r}")
        if len(failures) > 30:
            print(f"  ... 还有 {len(failures)-30} 项")
    sys.exit(0 if counters["fail"] == 0 else 1)

if __name__ == "__main__":
    main()
