import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProbabilityTrend } from "@/components/charts/ProbabilityTrend";
import type {
  ProbabilityHistorySeries,
  ProbabilityHistorySeriesRequest,
} from "@/lib/api";

type IntersectionCallback = (entries: Array<{ isIntersecting: boolean }>) => void;

const {
  apiMock,
  chartInitMock,
  chartSetOptionMock,
  chartResizeMock,
  chartDisposeMock,
} = vi.hoisted(() => ({
  apiMock: {
    getEventProbabilityHistory: vi.fn<(tokenId: string) => Promise<Array<{ t: number; p: number }>>>(),
    getEventProbabilityHistories: vi.fn<
      (series: ProbabilityHistorySeriesRequest[]) => Promise<ProbabilityHistorySeries[]>
    >(),
  },
  chartInitMock: vi.fn(),
  chartSetOptionMock: vi.fn(),
  chartResizeMock: vi.fn(),
  chartDisposeMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

vi.mock("@/lib/echarts", () => ({
  echarts: {
    init: chartInitMock,
  },
}));

const COLORS = ["#8BC1FF", "#2D9CFF", "#FFC21A", "#FF861A", "#B78CFF"];

const requests: ProbabilityHistorySeriesRequest[] = [
  { label: "不变", token_id: "same" },
  { label: "上涨", token_id: "up" },
  { label: "下跌", token_id: "down" },
  { label: "高位", token_id: "high" },
  { label: "低位", token_id: "low" },
  { label: "第六", token_id: "sixth" },
];

let intersectionCallbacks: IntersectionCallback[] = [];

function triggerIntersecting() {
  act(() => {
    for (const callback of intersectionCallbacks) {
      callback([{ isIntersecting: true }]);
    }
  });
}

function successfulSeries(): ProbabilityHistorySeries[] {
  return [
    {
      label: "不变",
      token_id: "same",
      points: [
        { t: 100, p: 0.7 },
        { t: 300, p: 0.71 },
      ],
      error: null,
    },
    {
      label: "上涨",
      token_id: "up",
      points: [
        { t: 200, p: 0.2 },
        { t: 300, p: 0.25 },
      ],
      error: null,
    },
    {
      label: "下跌",
      token_id: "down",
      points: [
        { t: 100, p: 0.4 },
        { t: 200, p: 0.35 },
      ],
      error: null,
    },
    {
      label: "高位",
      token_id: "high",
      points: [{ t: 300, p: 0.82 }],
      error: null,
    },
    {
      label: "低位",
      token_id: "low",
      points: [{ t: 200, p: 0.11 }],
      error: null,
    },
  ];
}

describe("ProbabilityTrend", () => {
  beforeEach(() => {
    intersectionCallbacks = [];
    chartSetOptionMock.mockClear();
    chartResizeMock.mockClear();
    chartDisposeMock.mockClear();
    chartInitMock.mockReset();
    chartInitMock.mockReturnValue({
      setOption: chartSetOptionMock,
      resize: chartResizeMock,
      dispose: chartDisposeMock,
    });
    apiMock.getEventProbabilityHistory.mockReset();
    apiMock.getEventProbabilityHistories.mockReset();
    apiMock.getEventProbabilityHistories.mockResolvedValue(successfulSeries());

    class MockIntersectionObserver {
      constructor(callback: IntersectionCallback) {
        intersectionCallbacks.push(callback);
      }

      observe = vi.fn();
      disconnect = vi.fn();
    }

    class MockResizeObserver {
      observe = vi.fn();
      disconnect = vi.fn();
    }

    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
    vi.stubGlobal("ResizeObserver", MockResizeObserver);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("renders empty state without requesting history when series is empty", () => {
    render(<ProbabilityTrend series={[]} />);

    expect(screen.getByText("暂无趋势数据")).toBeTruthy();
    expect(apiMock.getEventProbabilityHistories).not.toHaveBeenCalled();
    expect(apiMock.getEventProbabilityHistory).not.toHaveBeenCalled();
  });

  it("lazy loads up to five series with the shared histories endpoint", async () => {
    render(<ProbabilityTrend series={requests} />);

    expect(screen.getByText("趋势图将在进入屏幕时加载")).toBeTruthy();
    expect(apiMock.getEventProbabilityHistories).not.toHaveBeenCalled();

    triggerIntersecting();

    await waitFor(() => {
      expect(apiMock.getEventProbabilityHistories).toHaveBeenCalledWith(requests.slice(0, 5));
    });
    expect(apiMock.getEventProbabilityHistory).not.toHaveBeenCalled();
  });

  it("renders five stable-color lines on a union timestamp axis without connecting null gaps", async () => {
    render(<ProbabilityTrend series={requests} />);

    triggerIntersecting();

    await waitFor(() => {
      expect(chartSetOptionMock).toHaveBeenCalled();
    });
    const option = chartSetOptionMock.mock.calls[chartSetOptionMock.mock.calls.length - 1]?.[0];

    expect(option.yAxis.min).toBe(0);
    expect(option.yAxis.max).toBe(100);
    expect(option.legend.type).toBe("scroll");
    expect(option.legend.top).toBe(0);
    expect(option.series).toHaveLength(5);
    expect(option.series.map((item: { name: string }) => item.name)).toEqual([
      "不变 71.0%",
      "上涨 25.0%",
      "下跌 35.0%",
      "高位 82.0%",
      "低位 11.0%",
    ]);
    expect(option.series.map((item: { lineStyle: { color: string } }) => item.lineStyle.color)).toEqual(
      COLORS,
    );
    expect(option.series.every((item: { connectNulls: boolean }) => item.connectNulls === false)).toBe(true);
    expect(option.series.map((item: { data: Array<number | null> }) => item.data)).toEqual([
      [70, null, 71],
      [null, 20, 25],
      [40, 35, null],
      [null, null, 82],
      [null, 11, null],
    ]);
    expect(document.querySelector(".h-72")).toBeTruthy();
  });

  it("shows a partial unavailable warning while rendering successful series", async () => {
    apiMock.getEventProbabilityHistories.mockResolvedValue([
      successfulSeries()[0],
      { label: "上涨", token_id: "up", points: [], error: "missing history" },
    ]);

    render(<ProbabilityTrend series={requests.slice(0, 2)} />);
    triggerIntersecting();

    expect(await screen.findByText("部分趋势数据不可用")).toBeTruthy();
    await waitFor(() => {
      expect(chartSetOptionMock).toHaveBeenCalled();
    });
    const option = chartSetOptionMock.mock.calls[chartSetOptionMock.mock.calls.length - 1]?.[0];
    expect(option.series).toHaveLength(1);
    expect(option.series[0].name).toBe("不变 71.0%");
  });

  it("does not reload histories when rerendered with equivalent series content", async () => {
    const initialSeries = requests.slice(0, 2);
    const { rerender } = render(<ProbabilityTrend series={initialSeries} />);

    triggerIntersecting();

    await waitFor(() => {
      expect(apiMock.getEventProbabilityHistories).toHaveBeenCalledTimes(1);
    });

    rerender(<ProbabilityTrend series={initialSeries.map((item) => ({ ...item }))} />);

    await act(async () => {});
    expect(apiMock.getEventProbabilityHistories).toHaveBeenCalledTimes(1);
  });

  it("starts observing when series changes from empty to non-empty", async () => {
    const { rerender } = render(<ProbabilityTrend series={[]} />);

    expect(screen.getByText("暂无趋势数据")).toBeTruthy();

    rerender(<ProbabilityTrend series={requests.slice(0, 2)} />);
    expect(screen.getByText("趋势图将在进入屏幕时加载")).toBeTruthy();

    triggerIntersecting();

    await waitFor(() => {
      expect(apiMock.getEventProbabilityHistories).toHaveBeenCalledTimes(1);
    });
  });

  it("shows an error state when all requested series fail", async () => {
    apiMock.getEventProbabilityHistories.mockResolvedValue([
      { label: "不变", token_id: "same", points: [], error: "no data" },
      { label: "上涨", token_id: "up", points: [], error: "timeout" },
    ]);

    render(<ProbabilityTrend series={requests.slice(0, 2)} />);
    triggerIntersecting();

    expect(await screen.findByText("趋势数据加载失败")).toBeTruthy();
    expect(chartSetOptionMock).not.toHaveBeenCalled();
  });
});
