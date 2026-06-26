import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { IndustryDetail } from "@/pages/IndustryDetail";

const { getIndustryQuotes } = vi.hoisted(() => ({ getIndustryQuotes: vi.fn() }));

getIndustryQuotes.mockResolvedValue({
  updated_at: "2026-06-26T09:30:00Z",
  success_count: 2,
  error_count: 0,
  rows: [{ code: "002371.SZ", name: "北方华创", segment: "半导体设备", price: 420, change_pct: 2.5, amount: null, market_cap: null, pe_ttm: null, pb: null, source: "Wind", error: null }],
});

vi.mock("@/lib/api", () => ({
  api: {
    getIndustries: vi.fn().mockResolvedValue({ industries: [{ slug: "semiconductor", name: "半导体", summary: "覆盖制造、设备与材料。", refreshable: true }] }),
    getIndustryReport: vi.fn().mockResolvedValue({ content: "# 半导体国产替代深度研究\n\n日期：2026-06-26\n\n## 一、核心结论\n\n景气复苏需要订单与盈利共同验证。\n\n| 方向 | 建议权重 | 代表公司 |\n| --- | ---: | --- |\n| 前道设备 | 24% | 北方华创 |\n\n## 三、Vibe Trading团队审查\n\n| 排名 | 细分链条 | 综合景气 |\n| ---: | --- | ---: |\n| 1 | 前道设备 | 90 |\n\n## 五、产业链分层：成本、卡点、核心科技\n\n| 环节 | 核心卡点 | 核心科技/能力 | 估值方法 | 代表公司 |\n| --- | --- | --- | --- | --- |\n| 前道设备 | 订单验收 | 刻蚀 | PE/PEG | 北方华创 |\n\n## 七、公司映射与梯队\n\n| 梯队 | 公司 | 产业链定位 | 入选理由 |\n| --- | --- | --- | --- |\n| 第一梯队 | 北方华创 | 前道设备 | 订单可验证 |\n\n## 八、投资机会排序与组合\n\n| 排名 | 方向 | 建议权重 | 代表公司 | 排序理由 | 主要风险 |\n| ---: | --- | ---: | --- | --- | --- |\n| 1 | 前道设备 | 24% | 北方华创 | 确定性高 | 估值高 |\n\n## 十、证伪条件与加减仓触发器\n\n证伪条件：\n\n1. 订单放缓。\n\n加仓触发器：\n\n1. 收入确认兑现。\n\n降仓触发器：\n\n1. 现金流恶化。" }),
    getIndustryQuotes,
  },
}));

it("prioritizes research summary and refreshes only the current industry company pool", async () => {
  render(<MemoryRouter initialEntries={["/industry-research/semiconductor"]}><Routes><Route path="/industry-research/:slug" element={<IndustryDetail />} /></Routes></MemoryRouter>);

  expect(await screen.findByRole("heading", { name: "半导体" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "核心结论" })).toBeInTheDocument();
  expect(screen.getByText("组合结构")).toBeInTheDocument();
  expect(screen.getByText("产业链卡位")).toBeInTheDocument();
  expect(screen.getByText("公司梯队")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "公司数据跟踪" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "刷新半导体行情" }));
  expect(await screen.findByText("002371.SZ")).toBeInTheDocument();
  expect(getIndustryQuotes).toHaveBeenCalledWith("semiconductor");
});
