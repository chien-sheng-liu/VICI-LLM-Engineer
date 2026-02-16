# Mockup: Analysis + Report Snapshot

This mockup represents a typical agent run (dry-run mode). Use it to align UI/UX
and to explain the storytelling flow during interviews.

```yaml
run_id: MOCK-ANALYSIS-001
ticker: 2330
company: 台積電
analysis:
  executive_summary: |
    台積電短期維持 AI 驅動的成長軌跡，情緒偏多但需留意匯率與資本支出節奏。
  drivers:
    - AI/HPC 需求推升先進製程稼動率
    - 法人調升 FY25 毛利率假設
  risks:
    - 匯率與地緣風險造成獲利波動
    - 客戶庫存去化放緩
  trader_notes:
    trend_score: 3.8
    momentum_score: 3.5
    volume_score: 4.1
  catalysts:
    - 3 月底法說會更新資本支出
    - 美國客戶新晶片 tape-out 時程
news_tab:
  summary: "新聞聚焦 AI 伺服器供應鏈與台幣升值壓力"
  items:
    - title: 分析師調升台積電目標價
      sentiment: 正向
    - title: 匯率波動恐侵蝕毛利
      sentiment: 負向
report_tab:
  kpis:
    price: 600
    change_percent: 1.2
    market_cap: 49_660_781_658_112
  watch_items:
    - metric: 毛利率
      suggested_check: 季增 > 50 bps
    - metric: AI/HPC 稼動率
      suggested_check: 大型客戶庫存週期
```

Feel free to duplicate this file for future mockups (e.g., RAG-library view,
backtesting dashboards). Keeping them under `docs/mockups/` prevents clutter at
the repo root.
