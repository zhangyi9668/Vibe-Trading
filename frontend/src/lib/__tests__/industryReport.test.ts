import { describe, expect, it } from "vitest";

import { analyzeIndustryReport } from "@/lib/industryReport";

const report = `# 半导体国产替代深度投研报告

日期：2026-06-26

## 一、核心结论

行业进入订单和利润验证阶段。

| 方向 | 建议权重 | 代表公司 |
| --- | ---: | --- |
| 前道设备 | 24% | 北方华创 |
| 材料 | 12% | 安集科技 |

## 三、Vibe Trading团队审查

| 排名 | 细分链条 | 综合景气 | Vibe判断 |
| ---: | --- | ---: | --- |
| 1 | 前道设备 | 90 | 核心底仓 |

## 五、产业链分层：成本、卡点、核心科技

| 环节 | 成本结构 | 核心卡点 | 核心科技/能力 | 估值方法 | 代表公司 |
| --- | --- | --- | --- | --- | --- |
| 前道设备 | 研发 | 订单验收 | 刻蚀 | PE/PEG | 北方华创 |

## 七、公司映射与梯队

| 梯队 | 公司 | 产业链定位 | 入选理由 |
| --- | --- | --- | --- |
| 第一梯队 | 北方华创 | 前道设备 | 订单可验证 |

## 八、投资机会排序与组合

| 排名 | 方向 | 建议权重 | 代表公司 | 排序理由 | 主要风险 |
| ---: | --- | ---: | --- | --- | --- |
| 1 | 前道设备 | 24% | 北方华创 | 确定性高 | 估值高 |

## 十、证伪条件与加减仓触发器

证伪条件：

1. 订单放缓。

加仓触发器：

1. 收入确认兑现。

降仓触发器：

1. 现金流恶化。`;

describe("analyzeIndustryReport", () => {
  it("turns the unified report sections and tables into dashboard data", () => {
    const result = analyzeIndustryReport(report);

    expect(result.date).toBe("2026-06-26");
    expect(result.conclusion).toContain("订单和利润验证");
    expect(result.allocation.rows[0]).toEqual(["前道设备", "24%", "北方华创"]);
    expect(result.chain.rows[0][2]).toBe("订单验收");
    expect(result.companies.rows[0][0]).toBe("第一梯队");
    expect(result.opportunities.rows[0][1]).toBe("前道设备");
    expect(result.triggers.add).toEqual(["收入确认兑现。"]);
    expect(result.triggers.reduce).toEqual(["现金流恶化。"]);
  });
});
