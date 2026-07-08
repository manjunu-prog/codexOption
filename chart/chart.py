"""
Option Terminal Pro
chart/chart.py
Updated v0.1
"""

from pathlib import Path
import json
import streamlit.components.v1 as components


class TradingChart:
    def __init__(self, chart_dir=None):
        self.chart_dir = Path(chart_dir) if chart_dir else Path(__file__).parent

    def _read(self, filename):
        return (self.chart_dir / filename).read_text(encoding="utf-8")

    def render(
        self,
        candles,
        volume,
        emas=None,
        ema=None,
        vwap=None,
        cpr=None,
        angle_market=None,
        alphatrend=None,
        fvg=None,
        zones=None,
        structure=None,
        symbol="",
        timeframe="",
        chart_id="",
        height=820,
    ):
        index_html = self._read("index.html")
        css = self._read("chart.css")
        chart_js = self._read("chart.js")
        toolbar_js = self._read("toolbar.js")
        drawings_js = self._read("drawings.js")
        indicators_js = self._read("indicators.js")

        if ema and not emas:
            emas = [{"period": 20, "data": ema}]

        init = f"""
<script>
window.addEventListener("load", function(){{
    if(window.ChartEngine){{
        window.ChartEngine.setMeta({json.dumps(symbol)}, {json.dumps(timeframe)}, {json.dumps(chart_id or symbol)});
        window.ChartEngine.setSummary({json.dumps((structure or {}).get("__summary", []))});
        if(window.ChartEngine.holdViewStore) window.ChartEngine.holdViewStore(1400);
        window.ChartEngine.setCandles({json.dumps(candles)});
        window.ChartEngine.setVolume({json.dumps(volume)});
    }}
    if(window.Indicators){{
        {f'window.Indicators.setEMAs({json.dumps(emas)});' if emas else ''}
        {f'window.Indicators.setVWAP({json.dumps(vwap)});' if vwap else ''}
        {f'window.Indicators.setCPR({json.dumps(cpr)});' if cpr else ''}
        {f'window.Indicators.setAngleMarket({json.dumps(angle_market)});' if angle_market else ''}
        {f'window.Indicators.setAlphaTrend({json.dumps(alphatrend)});' if alphatrend else ''}
        {f'window.Indicators.setFVG({json.dumps(fvg)});' if fvg else ''}
        {f'window.Indicators.setZones({json.dumps(zones)});' if zones else ''}
        {f'window.Indicators.setStructure({json.dumps(structure)});' if structure else ''}
        if(window.ChartEngine && window.ChartEngine.preserveView){{
            window.ChartEngine.preserveView();
            setTimeout(()=>window.ChartEngine.preserveView(), 150);
            setTimeout(()=>window.ChartEngine.preserveView(), 450);
            setTimeout(()=>window.ChartEngine.preserveView(), 900);
        }}
    }}
}});
</script>
"""

        page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{index_html}
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script>{chart_js}</script>
<script>{toolbar_js}</script>
<script>{drawings_js}</script>
<script>{indicators_js}</script>
{init}
</body>
</html>"""

        components.html(page, height=height, scrolling=False)
