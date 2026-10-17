"""Render final, inspectable benchmark tables and static figures.

Run after benchmark completion with Matplotlib available (a temporary target
installation is sufficient; it is not an application dependency).
"""
from pathlib import Path
import csv
import hashlib
import json
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "evaluation/workbench-2026-10-17"
NAMES = {"normal_operations":"日常运营", "battery_truck_access_2024":"局部道路中断", "terminal_data_disruption_2017":"数据与运营中断", "long_dwell_backlog_2021":"长滞箱拥堵", "weather_warning_no_closure_2023":"天气预警对照", "equal_service_control":"等服务控制"}
ENGLISH = {"normal_operations":"Normal operations", "battery_truck_access_2024":"Access disruption", "terminal_data_disruption_2017":"Data disruption", "long_dwell_backlog_2021":"Long-dwell backlog", "weather_warning_no_closure_2023":"Warning, no closure", "equal_service_control":"Equal-service control"}
STRATEGIES = ("fifo", "priority", "optimized")


def fmt(value):
    return f"{value:.2f}"


def main():
    summary=json.loads((DATA/"summary.json").read_text())
    metadata=json.loads((DATA/"metadata.json").read_text())
    rows=[json.loads(line)for line in (DATA/"runs.jsonl").read_text().splitlines()]
    if not summary["complete"]:
        raise SystemExit("Matrix is incomplete; keep the report marked in progress")
    keys=[(r["scenario_id"],r["seed"],r["strategy"],r["horizon_minutes"])for r in rows]
    if len(keys)!=len(set(keys)):
        raise SystemExit("Duplicate raw checkpoint keys require investigation")
    audit={"rows":len(rows),"unique_rows":len(set(keys)),"failed_rows":len(summary["failures"]),"pair_mismatches":len(summary["world_pair_mismatches"]),
           "trace_audit_errors":sum(len(r.get("independent_trace_audit_errors",[]))for r in rows),
           "future_curve_errors":sum(any(p["minute"]>r["horizon_minutes"]for p in r.get("curves",[]))for r in rows),
           "negative_control_failures":[{k:r[k]for k in ("scenario_id","seed","strategy","horizon_minutes","completed_handoffs")}for r in rows if r["scenario_id"]=="equal_service_control" and r["status"]=="ok" and r["completed_handoffs"]!=min(100,2*(r["horizon_minutes"]//5))]}
    (DATA/"validation.json").write_text(json.dumps(audit,indent=2)+"\n")
    if any(audit[k]for k in ("failed_rows","pair_mismatches","trace_audit_errors","future_curve_errors","negative_control_failures")):
        raise SystemExit(f"Validation failed; report needs revision: {audit}")
    records=[]
    tables=["## 完整矩阵结果", "", "下面按预定的全部场景与两个观察窗口列出结果，没有挑选获胜场景。单位为每次合成运行完成的最终交接数，FIFO / Priority / CP 分别为先到先服务、紧急度和约束优化。区间为 CP−FIFO 配对均值差的 95% bootstrap 百分位区间。", "",
            "| 场景 | 分钟 | 每策略种子数 | FIFO | Priority | CP | CP−FIFO〔95%区间〕 | CP 相对 FIFO 赢 / 平 / 输 |", "|---|---:|---:|---:|---:|---:|---|---|" ]
    for comparison in summary["comparisons"]:
        scenario,horizon=comparison["scenario_id"],comparison["horizon_minutes"]
        methods=comparison["strategies"]
        if any(method not in methods for method in STRATEGIES):
            raise SystemExit("Missing strategy in a complete matrix")
        means=[methods[m]["metrics"]["completed_handoffs"]["mean"]for m in STRATEGIES]
        paired=next(p for p in comparison["paired"]if p["baseline"]=="fifo")
        delta=paired["differences_optimized_minus_baseline"]["completed_handoffs"]
        ci=delta["bootstrap_percentile_95_ci"]
        interval=f"{fmt(delta['mean_difference'])}〔{fmt(ci[0])}, {fmt(ci[1])}〕" if ci else f"{fmt(delta['mean_difference'])}〔n=3，不计算区间〕"
        tables.append(f"| {NAMES[scenario]} | {horizon} | {methods['fifo']['runs']} | {fmt(means[0])} | {fmt(means[1])} | {fmt(means[2])} | {interval} | {delta['positive']} / {delta['zero']} / {delta['negative']} |")
        records.append({"scenario_id":scenario,"horizon_minutes":horizon,"n":methods["fifo"]["runs"],"fifo_completed_mean":means[0],"priority_completed_mean":means[1],"optimized_completed_mean":means[2],"paired_completed_delta":delta["mean_difference"],"paired_delta_ci_low":ci[0]if ci else None,"paired_delta_ci_high":ci[1]if ci else None,"improved":delta["positive"],"tied":delta["zero"],"worse":delta["negative"]})
    tables += ["", "![配对完成交接数差与区间](../evaluation/workbench-2026-10-17/paired-throughput-differences.png)", "", "图中零线表示持平；同一横轴比例用于两个观察窗口。控制场景只有 3 个确定性种子，不绘制置信区间。", "", "## 等待、积压与服务组取舍", "", "等待值是每次运行统计值的跨运行均值：因此表中‘P90均值’并非把所有货柜混在一起重新求一个 P90。组间差距包含阻塞与未完成对象，不能解释为硬性公平承诺。", "", "| 场景 / 分钟 | 平均等待 FIFO / Priority / CP | P90 等待均值 FIFO / Priority / CP | 未完成积压 FIFO / Priority / CP | 组间均值差距 FIFO / Priority / CP |", "|---|---|---|---|---|" ]
    for c in summary["comparisons"]:
        def vals(metric):
            return " / ".join(fmt(c["strategies"][s]["metrics"][metric]["mean"])for s in STRATEGIES)
        tables.append(f"| {NAMES[c['scenario_id']]} / {c['horizon_minutes']} | {vals('avg_wait_minutes')} | {vals('p90_wait_minutes')} | {vals('unfinished_backlog')} | {vals('service_group_mean_wait_spread')} |")
    tables += ["", "未完成对象的等待下界均值、最大值、每个服务组的到达 / 完成数及等待均值 / 最大值，均保存在逐运行原始记录。选择策略时应同时检查这些值；只比较完成样本等待可能受选择和截尾影响。", "", "## 验证、运行开销与复现边界", ""]
    full=[r for r in rows if r["horizon_minutes"]==240]
    fallbacks=sum(r["solver_fallbacks"]for r in full)
    rejects=sum(r["plan_validation_rejections"]for r in full)
    tables += [f"共完成 {len(full)} 个策略世界、{len(rows)} 个检查点；原始失败 {len(summary['failures'])}、配对世界摘要不匹配 {len(summary['world_pair_mismatches'])}、独立实际轨迹审计错误 {audit['trace_audit_errors']}。最终窗口累计计划回退 {fallbacks} 次、计划验证拒绝 {rejects} 次。两个检查点来自同一世界，因此求解次数及回退总数只按 240 分钟记录累计，不把前 90 分钟重复相加。", "",
               f"本次矩阵实际墙钟耗时 {metadata.get('this_invocation_wall_seconds',0):.1f} 秒，两个进程并行执行。单世界运行时间与每次求解状态保留在原始记录。求解的墙钟预算会受机器负载影响；即使世界样本相同，也不保证在另一台机器或另一负载下得到相同的 CP 解。", "", "### 各策略 240 分钟运行墙钟时间", "", "| 策略 | 世界数 | 均值（秒） | 最大（秒） | 回退数 |", "|---|---:|---:|---:|---:|" ]
    for method in STRATEGIES:
        selected=[r for r in full if r["strategy"]==method]
        tables.append(f"| {method} | {len(selected)} | {statistics.mean(r['wall_seconds']for r in selected):.3f} | {max(r['wall_seconds']for r in selected):.3f} | {sum(r['solver_fallbacks']for r in selected)} |")
    tables += ["", "所有场景使用同一个 throughput 配置；本矩阵没有把 balanced/recovery 配置另当作已验证的优胜策略。技术差异来自可选区间、共同资源、任务依赖、滚动观察和共同执行守卫；本实验不能把不同指标的变化归因于某一个单独机制。", "", "### 保留的预检记录", "", "初次预检发现第 90 分钟曲线引用了后来继续增长的列表。数值指标未受影响；修正为检查点曲线副本后，重新运行完整矩阵。预检记录及原始脚本保存在 `evaluation/workbench-preflight-2026-10-17/`，不纳入最终估计。这个排除基于预先发现的记录格式缺陷，而非运行结果好坏。", "", "### 验收结论的范围", "", "本结果支持‘这个合成模型中的约束调度可以运行、可以接受同条件比较，并会呈现改善、持平及取舍’，不支持‘商业系统没有这些功能’或‘真实港口一定达到相同比例增益’。是否投入真实运行仍需账号覆盖核验、现场权限与资源接入以及受控试点。" ]
    document=ROOT/"docs/simulation-evaluation.zh-CN.md"
    text=document.read_text()
    start=text.index("\n\n") + 2
    end=text.index("\n\n## 实验回答什么",start)
    text=text[:start]+f"完整预定矩阵已运行并通过独立数据检查：{len(full)} 个策略世界、{len(rows)} 个 90/240 分钟检查点。全部结果、失败检查和来源信息见 [summary.json](../evaluation/workbench-2026-10-17/summary.json)、[runs.jsonl](../evaluation/workbench-2026-10-17/runs.jsonl)、[metadata.json](../evaluation/workbench-2026-10-17/metadata.json) 及 [validation.json](../evaluation/workbench-2026-10-17/validation.json)。"+text[end:]
    if "\n## 完整矩阵结果"in text:
        text=text.split("\n## 完整矩阵结果")[0]
    document.write_text(text+"\n\n"+"\n".join(tables)+"\n")
    with(DATA/"comparison-summary.csv").open("w")as handle:
        writer=csv.DictWriter(handle,fieldnames=records[0]);writer.writeheader();writer.writerows(records)
    plot(summary)
    (DATA/"report-render-metadata.json").write_text(json.dumps({"renderer_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"source_summary_sha256":hashlib.sha256((DATA/"summary.json").read_bytes()).hexdigest(),"figure":"paired-throughput-differences.png","note":"No metrics or raw outcomes were modified when rendering."},indent=2)+"\n")
    print(json.dumps(audit,ensure_ascii=False))


def plot(summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(1,2,figsize=(11.5,5),sharex=True,sharey=True)
    order=list(NAMES)
    max_extent=1
    for c in summary["comparisons"]:
        p=next(p for p in c["paired"]if p["baseline"]=="fifo")
        d=p["differences_optimized_minus_baseline"]["completed_handoffs"]
        values=(d["bootstrap_percentile_95_ci"]or[d["mean_difference"]])
        max_extent=max(max_extent,max(abs(v)for v in values))
    for ax,horizon in zip(axes,(90,240)):
        ax.axvline(0,color="#7b8794",linestyle="--",linewidth=1)
        for i,scenario in enumerate(order):
            c=next(c for c in summary["comparisons"]if c["scenario_id"]==scenario and c["horizon_minutes"]==horizon)
            p=next(p for p in c["paired"]if p["baseline"]=="fifo")
            d=p["differences_optimized_minus_baseline"]["completed_handoffs"]
            mean=d["mean_difference"];ci=d["bootstrap_percentile_95_ci"]
            color="#1b628c"if mean>=0 else"#b34b44"
            if ci:
                ax.errorbar(mean,i,xerr=[[max(0,mean-ci[0])],[max(0,ci[1]-mean)]],fmt="o",color=color,capsize=4,markersize=6)
            else:
                ax.plot(mean,i,"D",color="#505b66",markersize=5)
            ax.annotate(f"{mean:+.2f}",(mean,i),xytext=(6,7),textcoords="offset points",fontsize=9,color=color)
        ax.set_title(f"Minute {horizon}",fontweight="bold")
        ax.set_xlim(-max_extent*1.25,max_extent*1.25)
        ax.set_xlabel("Completed handoffs: CP-SAT minus FIFO")
        ax.grid(axis="x",alpha=.15)
    axes[0].set_yticks(range(len(order)),[ENGLISH[s]for s in order]);axes[0].invert_yaxis()
    fig.suptitle("Paired synthetic policy comparison · mean difference and 95% bootstrap interval",fontsize=12,fontweight="bold")
    fig.text(.5,.015,"30 paired seeds per non-control scenario; control n=3 (no interval). Synthetic model only; no commercial-product benchmark.",ha="center",fontsize=8,color="#505b66")
    fig.tight_layout(rect=(0,.055,1,.95))
    fig.savefig(DATA/"paired-throughput-differences.png",dpi=180)
    fig.savefig(DATA/"paired-throughput-differences.pdf")
    plt.close(fig)


if __name__=="__main__":
    main()
