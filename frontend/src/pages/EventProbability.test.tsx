import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EventProbability } from "@/pages/EventProbability";
import type {
  ProbabilityOverview,
  ProbabilityRefreshState,
} from "@/lib/api";

const overview: ProbabilityOverview = {
  as_of: "2026-06-14T00:00:00Z",
  events: [
    {
      question: "Will the Fed cut rates?",
      question_zh: "美联储会降息吗？",
      topic: "monetary_policy",
      outcomes: ["Yes", "No"],
      prices: [0.62, 0.38],
      prob_yes: 0.62,
      pick_label: "Yes",
      change_24h: 0.03,
      change_7d: 0.04,
      volume_24h: 120000,
      liquidity: 400000,
      end_date: "2026-09-18",
      slug: "fed-cut",
      series_ticker: null,
      token_id_yes: "fed-yes",
      source: "polymarket",
      source_category: "Economy",
    },
    {
      question: "Will CPI cool this month?",
      question_zh: "CPI 本月会回落吗？",
      topic: "macro_economy",
      outcomes: ["Yes", "No"],
      prices: [0.55, 0.45],
      prob_yes: 0.55,
      pick_label: null,
      change_24h: -0.02,
      change_7d: -0.01,
      volume_24h: 90000,
      liquidity: 100000,
      end_date: null,
      slug: "cpi-cool",
      series_ticker: "KXCPI",
      token_id_yes: null,
      source: "kalshi",
      source_category: "Economics",
    },
    {
      question: "OpenAI release this quarter?",
      question_zh: null,
      topic: "ai_technology",
      outcomes: ["Yes", "No"],
      prices: [0.44, 0.56],
      prob_yes: 0.44,
      pick_label: null,
      change_24h: 0.0,
      change_7d: 0.0,
      volume_24h: 5000,
      liquidity: 9000,
      end_date: null,
      slug: "openai-release",
      series_ticker: null,
      token_id_yes: null,
      source: "kalshi",
      source_category: "Science and Technology",
    },
  ],
  sources: [],
  translation_cache_size: 2,
  refresh: {
    status: "idle",
    kind: null,
    stage: null,
    progress_current: 0,
    progress_total: 0,
    started_at: null,
    finished_at: null,
    error: null,
    translation: { new_translations: 0, cache_hits: 0, pending: 0 },
  },
};

let statusQueue: ProbabilityRefreshState[] = [];

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getEventProbabilityOverview: vi.fn<() => Promise<ProbabilityOverview>>(),
    startEventProbabilityRefresh: vi.fn<
      (kind: "quick" | "full") => Promise<ProbabilityRefreshState>
    >(),
    getEventProbabilityRefreshStatus: vi.fn<() => Promise<ProbabilityRefreshState>>(),
    getEventProbabilityHistory: vi.fn<
      (tokenId: string) => Promise<Array<{ t: number; p: number }>>
    >(),
  },
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

vi.mock("@/components/charts/ProbabilityTrend", () => ({
  ProbabilityTrend: ({ tokenId }: { tokenId: string }) => (
    <div data-testid="probability-trend">{tokenId}</div>
  ),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <EventProbability />
    </MemoryRouter>,
  );
}

describe("EventProbability", () => {
  beforeEach(() => {
    statusQueue = [];
    apiMock.getEventProbabilityOverview.mockResolvedValue(overview);
    apiMock.startEventProbabilityRefresh.mockImplementation(async () => ({
      status: "queued",
      kind: "quick",
      stage: "fetching_polymarket",
      progress_current: 0,
      progress_total: 0,
      started_at: null,
      finished_at: null,
      error: null,
      translation: { new_translations: 0, cache_hits: 0, pending: 0 },
    }));
    apiMock.getEventProbabilityRefreshStatus.mockImplementation(async () => {
      return (
        statusQueue.shift() ?? {
          status: "done",
          kind: "quick",
          stage: "saving",
          progress_current: 0,
          progress_total: 0,
          started_at: null,
          finished_at: null,
          error: null,
          translation: { new_translations: 0, cache_hits: 0, pending: 0 },
        }
      );
    });
    apiMock.getEventProbabilityHistory.mockResolvedValue([
      { t: 1, p: 0.62 },
      { t: 2, p: 0.64 },
    ]);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    cleanup();
  });

  it("renders grouped sections with chinese titles and english fallback", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "货币政策" }),
    ).toBeTruthy();
    expect(screen.getByText("美联储会降息吗？")).toBeTruthy();
    expect(screen.getByText("Will the Fed cut rates?")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "AI 科技" })).toBeTruthy();
    expect(screen.getByText("OpenAI release this quarter?")).toBeTruthy();
  });

  it("filters by keyword, source, module and absolute change", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("美联储会降息吗？");

    await user.type(screen.getByLabelText("搜索"), "CPI");
    expect(screen.getByText("CPI 本月会回落吗？")).toBeTruthy();
    expect(screen.queryByText("美联储会降息吗？")).toBeNull();

    await user.clear(screen.getByLabelText("搜索"));
    await user.selectOptions(screen.getByLabelText("来源"), "polymarket");
    expect(screen.getByText("美联储会降息吗？")).toBeTruthy();
    expect(screen.queryByText("CPI 本月会回落吗？")).toBeNull();

    await user.selectOptions(screen.getByLabelText("来源"), "all");
    await user.selectOptions(screen.getByLabelText("模块"), "ai_technology");
    expect(screen.getByText("OpenAI release this quarter?")).toBeTruthy();
    expect(screen.queryByText("美联储会降息吗？")).toBeNull();

    await user.selectOptions(screen.getByLabelText("模块"), "all");
    await user.selectOptions(screen.getByLabelText("最小 24h 波动"), "0.02");
    expect(screen.getByText("美联储会降息吗？")).toBeTruthy();
    expect(screen.getByText("CPI 本月会回落吗？")).toBeTruthy();
    expect(screen.queryByText("OpenAI release this quarter?")).toBeNull();
  });

  it(
    "starts quick refresh and polls while keeping cached rows visible",
    async () => {
    statusQueue = [
      {
        status: "running",
        kind: "quick",
        stage: "fetching_kalshi",
        progress_current: 2,
        progress_total: 30,
        started_at: null,
        finished_at: null,
        error: null,
        translation: { new_translations: 0, cache_hits: 0, pending: 0 },
      },
      {
        status: "done",
        kind: "quick",
        stage: "saving",
        progress_current: 0,
        progress_total: 0,
        started_at: null,
        finished_at: null,
        error: null,
        translation: { new_translations: 0, cache_hits: 0, pending: 0 },
      },
    ];

    renderPage();
    await screen.findByText("美联储会降息吗？");
    vi.useFakeTimers();
      await act(async () => {
        screen.getByRole("button", { name: "快速刷新" }).click();
      });
      expect(apiMock.startEventProbabilityRefresh).toHaveBeenCalledWith("quick");
      expect(screen.getByText("美联储会降息吗？")).toBeTruthy();
      await act(async () => {});
      expect(screen.getByText("快速刷新进行中")).toBeTruthy();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1600);
      });
      expect(apiMock.getEventProbabilityRefreshStatus).toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1600);
      });
      expect(apiMock.getEventProbabilityOverview).toHaveBeenCalledTimes(2);
    },
    10000,
  );

  it("shows trend toggle only for polymarket rows with token id", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("美联储会降息吗？");

    const trendButton = screen.getByRole("button", { name: "查看趋势" });
    await user.click(trendButton);
    expect(screen.getByTestId("probability-trend").textContent).toContain("fed-yes");
    expect(screen.getByRole("button", { name: "查看趋势" })).toBeTruthy();
    expect(screen.queryByText("KXCPI")).toBeTruthy();
  });

  it("renders footer disclaimer", async () => {
    renderPage();
    expect(await screen.findByText("风险温度计，不构成交易信号")).toBeTruthy();
  });
});
