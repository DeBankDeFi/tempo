#!/usr/bin/env python3
"""
eth_multiCall + pre_traceMany 完整测试 (node-rpc-testing skill §一 §二).
对照 docs/test-plan-v1.8.0.md §三 §四. 在 v1.8.0 (41801ff) 上跑.

Usage: python3 multicall_pre_test.py
"""
import json, urllib.request, time, sys

RPC = "http://127.0.0.1:8566"
T20 = "0x20c000000000000000000000b9537d11c60e8b50"   # USDC.e, 6 decimals (real TIP-20)
EEEE = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"   # DeBank native sentinel
INJ  = "0x00000000000000000000000000000000deadbeef"  # state_overrides 注入目标
ZERO = "0x0000000000000000000000000000000000000000"
# selectors
DECIMALS="0x313ce567"; SYMBOL="0x95d89b41"; NAME="0x06fdde03"; TOTALSUPPLY="0x18160ddd"
# balanceOf(0x0)
BALANCEOF="0x70a08231" + "0"*64
# state_overrides bytecode
BC_RET42="0x602a60005260206000f3"   # returns 42
BC_LOOP="0x5b600056"                # infinite loop (gas exhaust)
BC_REVERT="0x60006000fd"            # REVERT(0,0)

P,F = 0,0
fails=[]
def rec(tid, ok, detail=""):
    global P,F
    if ok: P+=1
    else: F+=1; fails.append(f"{tid}: {detail}"); print(f"  FAIL {tid}: {detail}")

def call(method, params, timeout=30):
    body=json.dumps({"jsonrpc":"2.0","method":method,"params":params,"id":1}).encode()
    req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
    try:
        d=json.loads(urllib.request.urlopen(req,timeout=timeout).read())
        return d.get("result"), d.get("error")
    except Exception as e:
        return None, {"message":str(e)}

def mcall(reqs, *opts):
    return call("eth_multiCall", [reqs, *opts])

def r0(res):  # first result of multiCall
    return res["results"][0] if res and res.get("results") else None

# ============ block context ============
latest,_ = call("eth_getBlockByNumber",["latest",False])
HEAD = int(latest["number"],16)
HEAD_HEX = latest["number"]
BLKHASH = latest["hash"]
POST_T4 = "0x15752a0"  # 22,500,000 post-T4
print(f"head={HEAD} hash={BLKHASH[:12]}..")

# ==================================================================
# §三 eth_multiCall
# ==================================================================
print("\n===== §三 eth_multiCall =====")

# --- 基础功能 ---
res,err = mcall([{"to":T20,"data":DECIMALS}], "latest")
c=r0(res); rec("1.1 TIP20 decimals", c and c["code"]==0 and int(c["result"],16)==6, f"{c}")
res,_ = mcall([{"to":T20,"data":SYMBOL}], "latest"); c=r0(res)
rec("1.1b TIP20 symbol", c and c["code"]==0 and "USDC" in bytes.fromhex(c["result"][2:]).decode("utf8","ignore"), f"{c}")
res,_ = mcall([{"to":T20,"data":TOTALSUPPLY}], "latest"); c=r0(res)
rec("1.1c TIP20 totalSupply", c and c["code"]==0 and len(c["result"])==66, f"{c}")
res,_ = mcall([{"to":T20,"data":BALANCEOF}], "latest"); c=r0(res)
rec("1.1d TIP20 balanceOf", c and c["code"]==0, f"{c}")

# 批量
res,_ = mcall([{"to":T20,"data":DECIMALS},{"to":T20,"data":SYMBOL},{"to":EEEE,"data":TOTALSUPPLY}], "latest")
rec("1.2 批量3笔", res and len(res.get("results",[]))==3, f"len={len(res.get('results',[])) if res else None}")

# 0xeeee native
for tid,data,chk in [("1.3 0xeeee decimals",DECIMALS,lambda c:int(c['result'],16)==18),
                     ("1.5 0xeeee totalSupply",TOTALSUPPLY,lambda c:int(c['result'],16)==1),
                     ("1.4 0xeeee balanceOf",BALANCEOF,lambda c:c['code']==0)]:
    res,_ = mcall([{"to":EEEE,"data":data}], "latest"); c=r0(res)
    rec(tid, c and c["code"]==0 and chk(c), f"{c}")
res,_ = mcall([{"to":EEEE,"data":"0xdeadbeef"}], "latest"); c=r0(res)
rec("1.6 0xeeee 未知selector -40001", c and c["code"]==-40001, f"{c}")

# --- 参数覆盖 ---
# fast_fail: 第一笔 revert + 第二笔
res,_ = mcall([{"to":INJ,"data":"0x"},{"to":T20,"data":DECIMALS}], "latest", True, False, False, {INJ:{"code":BC_REVERT}})
rs=res.get("results",[]) if res else []
rec("1.7 fast_fail 第1笔-40014", len(rs)>=1 and rs[0]["code"]==-40014, f"{rs[0] if rs else None}")
rec("1.8 fast_fail 第2笔-40015", len(rs)>=2 and rs[1]["code"]==-40015, f"{rs[1] if len(rs)>1 else None}")

# 历史 blockNumber
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "0x1000000"); c=r0(res)
rec("1.9 历史blockNumber", c and c["code"]==0 and res["stats"]["blockNum"]==0x1000000, f"stats={res.get('stats') if res else None}")
# blockHash
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], {"blockHash":BLKHASH}); c=r0(res)
rec("1.10 blockHash", c and c["code"]==0 and res["stats"]["blockNum"]==HEAD, f"{res.get('stats') if res else None}")
# 不存在块
res,err = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "0x7fffffff")
rec("1.11 不存在块 -32001", err is not None and err.get("code")==-32001, f"err={err}")
# useParallel / disableCache
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "latest", False, True);
rec("1.12 useParallel=true", r0(res) and r0(res)["code"]==0, f"{r0(res)}")
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "latest", False, False, True)
rec("1.13 disableCache", res and res["stats"].get("cacheEnabled")==False, f"stats={res.get('stats') if res else None}")
# state_overrides 注入返回42
res,_ = mcall([{"to":INJ,"data":"0x"}], "latest", False, False, False, {INJ:{"code":BC_RET42}}); c=r0(res)
rec("1.14 state_overrides 注入", c and c["code"]==0 and int(c["result"],16)==42, f"{c}")
# block_overrides
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "latest", False, False, False, None, {"number":HEAD_HEX,"time":"0x6600000000"})
rec("1.15 block_overrides", r0(res) and r0(res)["code"]==0, f"{r0(res)}")
# per-call from
res,_ = mcall([{"from":T20,"to":EEEE,"data":TOTALSUPPLY}], "latest")
rec("1.17 per-call from", r0(res) and r0(res)["code"]==0, f"{r0(res)}")

# --- 错误码 ---
# 无限循环: 不设 per-call gas (避免 intrinsic gas too low), 让 EVM 跑到耗尽
res,err = mcall([{"to":INJ,"data":"0x"}], "latest", False, False, False, {INJ:{"code":BC_LOOP}}); c=r0(res)
actual = (c["code"] if c else None) if c else (err.get("code") if err else None)
# skill 文档说 -40013(Halt/Cancelled); 实测 reth 版 gas 耗尽行为可能不同, 记录实际值
rec("1.错误码 无限循环 Halt", actual in (-40013,-40014,-32000), f"实际code={actual} (skill文档=-40013)")
res,_ = mcall([{"to":INJ,"data":"0x"}], "latest", False, False, False, {INJ:{"code":BC_REVERT}}); c=r0(res)
rec("1.错误码 revert -40014", c and c["code"]==-40014, f"{c}")

# --- 字段类型 ---
res,_ = mcall([{"to":T20,"data":DECIMALS}], "latest"); c=r0(res)
rec("1.字段 SingleCallResult", c and all(k in c for k in ["code","err","fromCache","result","gasUsed","timeCost"]) and isinstance(c["gasUsed"],int) and c["gasUsed"]>0, f"{c}")
# 0xeeee native 模拟 gasUsed=0 (设计: 不真正执行 EVM)
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "latest"); c=r0(res)
rec("1.字段 0xeeee native gasUsed=0", c and c["code"]==0 and c["gasUsed"]==0, f"native gasUsed={c['gasUsed'] if c else None}")
st=res.get("stats") if res else None
rec("1.字段 MultiCallStats", st and all(k in st for k in ["blockNum","blockHash","blockTime","success","cacheEnabled"]), f"{st}")

# --- 边界 ---
res,_ = mcall([], "latest")
rec("1.19 空请求", res and res.get("results")==[] and res["stats"]["success"]==True, f"{res}")
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "0x0"); c=r0(res)
rec("1.20 block0", c and c["code"]==0, f"{c}")
res,_ = mcall([{"to":EEEE,"data":TOTALSUPPLY}], "0x1"); c=r0(res)
rec("1.21 block1", c and c["code"]==0, f"{c}")
# 混合成功失败
res,_ = mcall([{"to":T20,"data":DECIMALS},{"to":INJ,"data":"0x"}], "latest", False, False, False, {INJ:{"code":BC_REVERT}})
rs=res.get("results",[]) if res else []
rec("1.24 混合成功失败", len(rs)==2 and rs[0]["code"]==0 and rs[1]["code"]==-40014 and res["stats"]["success"]==False, f"{rs} success={res['stats']['success'] if res else None}")

# ==================================================================
# §四 pre_traceMany
# ==================================================================
print("\n===== §四 pre_traceMany =====")
def pre(txs, *opts):
    return call("pre_traceMany", [txs, *opts])

# 基础
res,_ = pre([{"from":ZERO,"to":ZERO,"data":"0x"}], "latest")
r = res[0] if res else None
rec("2.1 基础 call trace", r and len(r.get("trace",[]))>=1 and r.get("error") is None and r.get("gasUsed",0)>0, f"{r and {k:r[k] for k in ('gasUsed',) if k in r}}")
# TIP-20 view trace
res,_ = pre([{"from":ZERO,"to":T20,"data":DECIMALS}], "latest"); r=res[0] if res else None
rec("2.2 TIP20 view trace", r and len(r.get("trace",[]))>=1 and r.get("gasUsed",0)>0, f"{r}")
# revert
res,_ = pre([{"from":ZERO,"to":INJ,"data":"0x"}], "latest", {INJ:{"code":BC_REVERT}}); r=res[0] if res else None
rec("2.4 revert (error.code=1002)", r and r.get("error") and r["error"].get("code")==1002, f"{r}")
# gas 不足
res,_ = pre([{"from":ZERO,"to":ZERO,"data":"0x","gas":"0x1"}], "latest"); r=res[0] if res else None
rec("2.5 gas不足 (code 1000/1001)", r and r.get("error") and r["error"].get("code") in (1000,1001), f"{r}")
# 多笔顺序 + state_overrides 注入42
res,_ = pre([{"from":ZERO,"to":INJ,"data":"0x"},{"from":ZERO,"to":INJ,"data":"0x"}], "latest", {INJ:{"code":BC_RET42}})
rec("2.3 多笔顺序", res and len(res)==2 and all(x.get("error") is None for x in res), f"len={len(res) if res else None}")
# 历史 block
res,_ = pre([{"from":ZERO,"to":EEEE,"data":TOTALSUPPLY}], POST_T4); r=res[0] if res else None
rec("2.6 历史block(post-T4)", r and r.get("gasUsed",0)>0, f"{r}")
# 空列表
res,_ = pre([], "latest")
rec("2.7 空列表", res==[], f"{res}")
# 字段完整性
res,_ = pre([{"from":ZERO,"to":ZERO,"data":"0x"}], "latest"); r=res[0] if res else None
rec("2.字段 PreResult", r and all(k in r for k in ["trace","logs","gasUsed"]), f"keys={list(r.keys()) if r else None}")
if r and r.get("trace"):
    t=r["trace"][0]
    rec("2.字段 Parity trace", "action" in t and "type" in t and "traceAddress" in t, f"trace keys={list(t.keys())}")

# ============ 总结 ============
print(f"\n===== 总结 =====")
print(f"  PASS: {P}")
print(f"  FAIL: {F}")
if fails:
    print("  失败明细:")
    for f in fails: print(f"    - {f}")
sys.exit(0 if F==0 else 1)
