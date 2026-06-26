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
    getIndustryReport: vi.fn().mockResolvedValue({ content: "# 半导体深度研究\n\n## 核心结论\n\n景气复苏需要订单与盈利共同验证。\n\n## 产业链分层\n\n设备与材料是重点。\n\n## 风险提示\n\n库存去化不及预期。" }),
    getIndustryQuotes,
  },
}));

it("prioritizes research summary and refreshes only the current industry company pool", async () => {
  render(<MemoryRouter initialEntries={["/industry-research/semiconductor"]}><Routes><Route path="/industry-research/:slug" element={<IndustryDetail />} /></Routes></MemoryRouter>);

  expect(await screen.findByRole("heading", { name: "半导体行业研究" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "核心结论" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "公司数据跟踪" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "刷新半导体行情" }));
  expect(await screen.findByText("北方华创")).toBeInTheDocument();
  expect(getIndustryQuotes).toHaveBeenCalledWith("semiconductor");
});
