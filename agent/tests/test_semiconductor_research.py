from __future__ import annotations

from src.semiconductor_research.service import SemiconductorQuoteService


def test_fetch_company_uses_ifind_first_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("IFIND_ACCESS_TOKEN", "configured")
    service = SemiconductorQuoteService()
    calls: list[str] = []

    def fake_ifind(company):
        calls.append("ifind")
        return {
            "code": company["code"],
            "name": company["name"],
            "segment": company["segment"],
            "price": 10.0,
            "change_pct": 1.2,
            "amount": 100.0,
            "market_cap": 1000.0,
            "pe_ttm": 20.0,
            "pb": 2.0,
            "source": "iFinD",
            "error": None,
        }

    def fake_wind(_company):
        calls.append("wind")
        raise AssertionError("Wind should not run after successful iFinD")

    monkeypatch.setattr(service, "call_ifind", fake_ifind)
    monkeypatch.setattr(service, "call_wind", fake_wind)

    row = service.fetch_company(service.companies[0])

    assert row["source"] == "iFinD"
    assert calls == ["ifind"]


def test_fetch_all_counts_successes_and_errors(monkeypatch) -> None:
    service = SemiconductorQuoteService(companies=[
        {"code": "000001.SZ", "ifind": "000001.SZ", "name": "成功公司", "segment": "设计/IP/AI"},
        {"code": "000002.SZ", "ifind": "000002.SZ", "name": "失败公司", "segment": "半导体设备"},
    ])

    def fake_fetch(company):
        return {
            "code": company["code"],
            "name": company["name"],
            "segment": company["segment"],
            "price": None,
            "change_pct": None,
            "amount": None,
            "market_cap": None,
            "pe_ttm": None,
            "pb": None,
            "source": "iFinD" if company["name"] == "成功公司" else "不可用",
            "error": None if company["name"] == "成功公司" else "upstream unavailable",
        }

    monkeypatch.setattr(service, "fetch_company", fake_fetch)

    payload = service.fetch_all(max_workers=2)

    assert payload["success_count"] == 1
    assert payload["error_count"] == 1
    assert [row["code"] for row in payload["rows"]] == ["000001.SZ", "000002.SZ"]


def test_fetch_all_uses_batch_ifind_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("IFIND_ACCESS_TOKEN", "configured")
    service = SemiconductorQuoteService(companies=[
        {"code": "000001.SZ", "ifind": "000001.SZ", "name": "公司A", "segment": "设计/IP/AI"},
        {"code": "000002.SZ", "ifind": "000002.SZ", "name": "公司B", "segment": "半导体设备"},
    ])
    calls: list[str] = []

    def fake_batch(companies):
        calls.append(",".join(item["code"] for item in companies))
        return [
            {
                "code": item["code"],
                "name": item["name"],
                "segment": item["segment"],
                "price": 10.0,
                "change_pct": 1.0,
                "amount": 100.0,
                "market_cap": 1000.0,
                "pe_ttm": 20.0,
                "pb": 2.0,
                "source": "iFinD",
                "error": None,
            }
            for item in companies
        ]

    monkeypatch.setattr(service, "call_ifind_batch", fake_batch)

    payload = service.fetch_all()

    assert payload["success_count"] == 2
    assert payload["error_count"] == 0
    assert calls == ["000001.SZ,000002.SZ"]
