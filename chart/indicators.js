/*
=========================================================
Option Terminal Pro
chart/indicators.js
Version 0.1
=========================================================
Indicator Rendering Engine
=========================================================
*/

class IndicatorEngine {

    constructor(chartEngine){

        this.chartEngine = chartEngine;

        this.chart = chartEngine.chart;
        this.series = {};
        this.zones = [];
        this.structureZones = [];
        this.alphaTrendFill = [];
        this.labels = [];
        this.zoneWatchFrame = null;
        this.alphaTrendFrame = null;
        this.lastZoneSignature = "";
        this.lastAlphaTrendSignature = "";
        this.alphaTrendLayer = this.createAlphaTrendLayer();
        this.zoneLayer = this.createZoneLayer();
        this.labelLayer = this.createLabelLayer();
        this.chart.timeScale().subscribeVisibleTimeRangeChange(()=>{
            this.renderAlphaTrendFill();
            this.renderZones();
            this.renderLabels();
        });
        window.addEventListener("resize",()=>{
            this.renderAlphaTrendFill();
            this.renderZones();
            this.renderLabels();
        });
        this.chartEngine.container.addEventListener("pointermove",()=>{
            this.scheduleAlphaTrendRender();
            this.scheduleZoneRender();
            this.scheduleLabelRender();
        });
        this.chartEngine.container.addEventListener("wheel",()=>{
            this.scheduleAlphaTrendRender();
            this.scheduleZoneRender();
            this.scheduleLabelRender();
        });

    }

    createZoneLayer(){

        const parent = this.chartEngine.container.parentElement;
        const layer = document.createElement("div");
        layer.className = "zoneLayer";
        parent.appendChild(layer);
        return layer;

    }

    createAlphaTrendLayer(){

        const parent = this.chartEngine.container.parentElement;
        const layer = document.createElement("div");
        layer.className = "alphaTrendLayer";
        parent.appendChild(layer);
        return layer;

    }

    createLabelLayer(){

        const parent = this.chartEngine.container.parentElement;
        const layer = document.createElement("div");
        layer.className = "labelLayer";
        parent.appendChild(layer);
        return layer;

    }

    // ------------------------------
    // Generic Line Indicator
    // ------------------------------
    addLine(name,data,color="#FFD54F",width=2){

        if(this.series[name]){
            this.chart.removeSeries(this.series[name]);
        }

        const cleanData = (data || []).filter(item =>
            item &&
            item.time != null &&
            Number.isFinite(item.value)
        );

        if(cleanData.length === 0) return;

        const line = this.chart.addLineSeries({
            color:color,
            lineWidth:width,
            lastValueVisible:true,
            crosshairMarkerVisible:false,
            priceLineVisible:false
        });

        line.setData(cleanData);

        this.series[name]=line;

    }

    // ------------------------------
    // EMA
    // data format:
    // [{time:...,value:...}]
    // ------------------------------
    setEMA(period,data){

        const colors={
            9:"#00E5FF",
            20:"#FFD600",
            50:"#FF9800",
            100:"#AB47BC",
            200:"#F44336"
        };

        this.addLine(
            "EMA_"+period,
            data,
            colors[period] || "#FFFFFF",
            2
        );

    }

    setEMAs(items){

        (items || []).forEach(item=>{
            this.setEMA(item.period,item.data);
        });

    }

    // ------------------------------
    // VWAP
    // ------------------------------
    setVWAP(data){

        this.addLine(
            "VWAP",
            data,
            "#00C853",
            2
        );

    }

    setAlphaTrend(data){

        if(!data) return;

        if(this.series.AlphaTrend_Body){
            this.chart.removeSeries(this.series.AlphaTrend_Body);
            delete this.series.AlphaTrend_Body;
        }

        this.setAlphaTrendFill(data.current || [], data.lag || []);

        this.addLine(
            "AlphaTrend",
            data.current || [],
            "#0022FC",
            4
        );

        this.addLine(
            "AlphaTrend_Lag",
            data.lag || [],
            "#FC0400",
            4
        );

        if(this.chartEngine && this.chartEngine.setMarkerSource){
            this.chartEngine.setMarkerSource("alphatrend", (data.markers || []).map(marker=>({
                ...marker,
                text:""
            })));
        }
        this.setLabels("alphatrend", (data.markers || []).map(marker=>({
            time:marker.time,
            price:marker.price,
            text:marker.text,
            tone:marker.text === "BUY" ? "buy" : "sell"
        })));

    }

    setAlphaTrendFill(current, lag){

        const lagByTime = new Map((lag || []).map(point=>[String(point.time), point.value]));
        let lastTone = "bullish";
        this.alphaTrendFill = (current || []).map(point=>{
            const lagValue = lagByTime.get(String(point.time));
            if(!Number.isFinite(point.value) || !Number.isFinite(lagValue)) return null;
            if(point.value > lagValue){
                lastTone = "bullish";
            }else if(point.value < lagValue){
                lastTone = "bearish";
            }
            return {
                time: point.time,
                current: point.value,
                lag: lagValue,
                tone: lastTone
            };
        }).filter(Boolean);

        this.renderAlphaTrendFill();
        setTimeout(()=>this.renderAlphaTrendFill(), 100);

    }

    // ------------------------------
    // Generic Indicator
    // ------------------------------
    setIndicator(name,data,color){

        this.addLine(name,data,color);

    }

    // ------------------------------
    // Remove Indicator
    // ------------------------------
    remove(name){

        if(!this.series[name]) return;

        this.chart.removeSeries(
            this.series[name]
        );

        delete this.series[name];

    }

    // ------------------------------
    // Remove All
    // ------------------------------
    clear(){

        Object.keys(this.series).forEach(key=>{

            this.chart.removeSeries(
                this.series[key]
            );

        });

        this.series={};

    }

    // ------------------------------
    // Future Hooks
    // ------------------------------

    setRSI(data){
        console.log("RSI Ready",data.length);
    }

    setMACD(macd,signal,histogram){
        console.log("MACD Ready");
    }

    setSuperTrend(data){
        console.log("SuperTrend Ready");
    }

    setBollinger(upper,middle,lower){
        console.log("BB Ready");
    }

    setFVG(boxes){

        (boxes || []).forEach((box,index)=>{
            if(!box || box.time == null || !Number.isFinite(box.from) || !Number.isFinite(box.to)) return;
            const mid = (box.from + box.to) / 2;
            if(!Number.isFinite(mid)) return;
            const color = box.direction === "bullish"
                ? "rgba(34,197,94,0.85)"
                : "rgba(239,68,68,0.85)";
            const line = this.chart.addLineSeries({
                color,
                lineWidth:2,
                lineStyle:LightweightCharts.LineStyle.Dotted,
                lastValueVisible:false,
                priceLineVisible:false,
                crosshairMarkerVisible:false
            });
            const last = (this.chartEngine.lastCandles || []).slice(-1)[0];
            line.setData([
                {time:box.time,value:mid},
                {time:last ? last.time : box.time,value:mid}
            ]);
            this.series["FVG_"+index]=line;
        });

    }

    setZones(zones){

        this.zones = (zones || []).filter(zone =>
            zone &&
            zone.startTime != null &&
            zone.endTime != null &&
            Number.isFinite(zone.top) &&
            Number.isFinite(zone.bottom)
        );

        this.renderZones();
        setTimeout(()=>this.renderZones(), 100);

    }

    scheduleZoneRender(){

        if(this.zoneWatchFrame != null || !this.zones || this.zones.length === 0) return;

        this.zoneWatchFrame = requestAnimationFrame(()=>{
            this.zoneWatchFrame = null;
            this.renderZones(false);
        });

    }

    scheduleAlphaTrendRender(){

        if(this.alphaTrendFrame != null || !this.alphaTrendFill || this.alphaTrendFill.length === 0) return;

        this.alphaTrendFrame = requestAnimationFrame(()=>{
            this.alphaTrendFrame = null;
            this.renderAlphaTrendFill(false);
        });

    }

    scheduleLabelRender(){

        if(!this.labels || this.labels.length === 0) return;
        requestAnimationFrame(()=>this.renderLabels());

    }

    renderAlphaTrendFill(force=true){

        if(!this.alphaTrendLayer || !this.chartEngine || !this.chartEngine.candleSeries) return;

        const points = this.alphaTrendFill || [];
        if(points.length < 2){
            this.alphaTrendLayer.innerHTML = "";
            this.lastAlphaTrendSignature = "";
            return;
        }

        const width = this.chartEngine.container.clientWidth || 1;
        const height = this.chartEngine.container.clientHeight || 1;
        const polygons = [];

        for(let index = 1; index < points.length; index++){
            const prev = points[index - 1];
            const current = points[index];
            const x1 = this.timeToCoordinate(prev.time);
            const x2 = this.timeToCoordinate(current.time);
            const yCurrent1 = this.chartEngine.candleSeries.priceToCoordinate(prev.current);
            const yCurrent2 = this.chartEngine.candleSeries.priceToCoordinate(current.current);
            const yLag1 = this.chartEngine.candleSeries.priceToCoordinate(prev.lag);
            const yLag2 = this.chartEngine.candleSeries.priceToCoordinate(current.lag);
            if([x1, x2, yCurrent1, yCurrent2, yLag1, yLag2].some(value=>value == null)) continue;
            if(Math.abs(x2 - x1) > width * 0.25) continue;

            polygons.push({
                tone: current.tone || prev.tone || "bullish",
                points: [
                    [x1, yCurrent1],
                    [x2, yCurrent2],
                    [x2, yLag2],
                    [x1, yLag1]
                ]
            });
        }

        const signature = polygons.map(item =>
            `${item.tone}:${item.points.map(([x,y])=>`${Math.round(x)},${Math.round(y)}`).join(";")}`
        ).join("|");

        if(!force && signature === this.lastAlphaTrendSignature) return;
        this.lastAlphaTrendSignature = signature;

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("width", String(width));
        svg.setAttribute("height", String(height));
        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.setAttribute("preserveAspectRatio", "none");

        polygons.forEach(item=>{
            const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            polygon.setAttribute("points", item.points.map(([x,y])=>`${x},${y}`).join(" "));
            polygon.setAttribute(
                "fill",
                item.tone === "bullish" ? "rgba(0,230,15,0.68)" : "rgba(128,0,11,0.72)"
            );
            polygon.setAttribute("stroke", "none");
            svg.appendChild(polygon);
        });

        this.alphaTrendLayer.innerHTML = "";
        this.alphaTrendLayer.appendChild(svg);

    }

    renderZones(force=true){

        if(!this.zoneLayer || !this.chartEngine || !this.chartEngine.candleSeries) return;

        const timeScale = this.chart.timeScale();
        const renderedZones = [];

        const allZones = [
            ...(this.zones || []),
            ...(this.structureZones || [])
        ];

        allZones.forEach(zone=>{

            const x1 = this.timeToCoordinate(zone.startTime);
            const x2 = this.timeToCoordinate(zone.endTime);
            const yTop = this.chartEngine.candleSeries.priceToCoordinate(zone.top);
            const yBottom = this.chartEngine.candleSeries.priceToCoordinate(zone.bottom);

            if(x1 == null || x2 == null || yTop == null || yBottom == null) return;

            const left = Math.min(x1, x2);
            const right = Math.max(x1, x2);
            const top = Math.min(yTop, yBottom);
            const bottom = Math.max(yTop, yBottom);
            const width = Math.max(right - left, 6);
            const height = Math.max(bottom - top, 4);

            renderedZones.push({zone, left, top, width, height});

        });

        const signature = renderedZones.map(item =>
            `${Math.round(item.left)}:${Math.round(item.top)}:${Math.round(item.width)}:${Math.round(item.height)}`
        ).join("|");

        if(!force && signature === this.lastZoneSignature) return;
        this.lastZoneSignature = signature;
        this.zoneLayer.innerHTML = "";

        renderedZones.forEach(({zone, left, top, width, height})=>{

            const box = document.createElement("div");
            box.className = `zoneBox ${zone.kind || ""} ${zone.direction || ""}`;
            box.style.left = `${left}px`;
            box.style.top = `${top}px`;
            box.style.width = `${width}px`;
            box.style.height = `${height}px`;
            box.style.background = zone.fill || "rgba(148,163,184,0.16)";
            box.style.borderColor = zone.border || "rgba(148,163,184,0.65)";
            box.style.borderStyle = zone.borderStyle || "solid";

            if(zone.label){
                const label = document.createElement("span");
                label.textContent = zone.label || "";
                label.style.color = zone.text || zone.border || "#e5e7eb";
                if(zone.labelPosition === "center"){
                    label.className = "centerLabel";
                }
                box.appendChild(label);
            }
            this.zoneLayer.appendChild(box);

        });

    }

    setLabels(source, labels){

        this.labels = [
            ...(this.labels || []).filter(label=>label.source !== source),
            ...(labels || []).filter(label =>
                label &&
                label.time != null &&
                Number.isFinite(label.price) &&
                label.text
            ).map(label=>({...label, source}))
        ];
        this.renderLabels();
        setTimeout(()=>this.renderLabels(), 100);

    }

    renderLabels(){

        if(!this.labelLayer || !this.chartEngine || !this.chartEngine.candleSeries) return;

        this.labelLayer.innerHTML = "";
        (this.labels || []).slice(-80).forEach(label=>{
            const x = this.timeToCoordinate(label.time);
            const y = this.chartEngine.candleSeries.priceToCoordinate(label.price);
            if(x == null || y == null) return;

            const el = document.createElement("div");
            el.className = `indicatorLabel ${label.source || ""} ${label.tone || ""}`;
            el.textContent = label.text;
            el.style.left = `${x}px`;
            el.style.top = `${y}px`;
            this.labelLayer.appendChild(el);
        });

    }

    timeToCoordinate(time){

        const direct = this.chart.timeScale().timeToCoordinate(time);
        if(direct != null) return direct;

        const candles = this.chartEngine.lastCandles || [];
        if(candles.length < 2 || time == null) return direct;

        let nearestIndex = 0;
        let nearestDistance = Math.abs(Number(candles[0].time) - Number(time));
        for(let i = 1; i < candles.length; i++){
            const distance = Math.abs(Number(candles[i].time) - Number(time));
            if(distance < nearestDistance){
                nearestDistance = distance;
                nearestIndex = i;
            }
        }

        const nearestCoordinate = this.chart.timeScale().timeToCoordinate(candles[nearestIndex].time);
        if(nearestCoordinate == null) return direct;

        const spacings = [];
        for(let i = 1; i < candles.length; i++){
            const prev = this.chart.timeScale().timeToCoordinate(candles[i - 1].time);
            const current = this.chart.timeScale().timeToCoordinate(candles[i].time);
            if(prev != null && current != null && current > prev){
                spacings.push(current - prev);
            }
        }

        if(spacings.length === 0) return direct;
        spacings.sort((a,b)=>a-b);
        const barSpacing = spacings[Math.floor(spacings.length / 2)];
        const seconds = this.inferTimeStep(candles);
        const offset = (Number(time) - Number(candles[nearestIndex].time)) / seconds;
        return nearestCoordinate + (offset * barSpacing);

    }

    inferTimeStep(candles){

        const deltas = [];
        for(let i = 1; i < candles.length; i++){
            const delta = Number(candles[i].time) - Number(candles[i - 1].time);
            if(Number.isFinite(delta) && delta > 0){
                deltas.push(delta);
            }
        }
        if(deltas.length === 0) return 300;
        deltas.sort((a,b)=>a-b);
        return deltas[Math.floor(deltas.length / 2)];

    }

    setOrderBlocks(blocks){
        console.log("OrderBlocks Ready");
    }

    setLiquidity(zones){
        console.log("Liquidity Ready");
    }

    setBOS(levels){
        console.log("BOS Ready");
    }

    setStructure(structure){

        if(!structure) return;

        this.removeByPrefix("STRUCTURE_");
        this.structureZones = (structure.zones || []).filter(zone =>
            zone &&
            zone.startTime != null &&
            zone.endTime != null &&
            Number.isFinite(zone.top) &&
            Number.isFinite(zone.bottom)
        ).map(zone=>({
            ...zone,
            label:"",
            labelPosition:"center"
        }));
        this.renderZones();

        if(this.chartEngine && structure.markers){
            this.chartEngine.setMarkerSource("structure", []);
        }

        this.setLabels("structure", (structure.levels || []).map(level=>({
            time:level.labelTime || level.endTime || level.time,
            price:level.price,
            text:level.label,
            tone:(level.color || "").includes("16a34a") || (level.color || "").includes("14b8a6") ? "bull" : "bear"
        })));

        (structure.levels || []).forEach((level,index)=>{
            if(!level || level.time == null || !Number.isFinite(level.price)) return;
            const line = this.chart.addLineSeries({
                color:level.color || "#9ca3af",
                lineWidth:2,
                lineStyle:level.style === "dashed" ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
                lastValueVisible:false,
                priceLineVisible:false,
                crosshairMarkerVisible:false
            });
            line.setData([
                {time:level.startTime || level.time,value:level.price},
                {time:level.endTime || level.time,value:level.price}
            ]);
            this.series["STRUCTURE_"+index]=line;
        });

        (structure.trendLines || []).forEach((line,index)=>{
            if(
                !line ||
                line.startTime == null ||
                line.endTime == null ||
                !Number.isFinite(line.startPrice) ||
                !Number.isFinite(line.endPrice)
            ) return;
            const trendLine = this.chart.addLineSeries({
                color:line.color || "rgba(20,184,166,0.72)",
                lineWidth:2,
                lastValueVisible:false,
                priceLineVisible:false,
                crosshairMarkerVisible:false
            });
            trendLine.setData([
                {time:line.startTime,value:line.startPrice},
                {time:line.endTime,value:line.endPrice}
            ]);
            this.series["STRUCTURE_TREND_"+index]=trendLine;
        });

    }

    removeByPrefix(prefix){

        Object.keys(this.series).forEach(key=>{
            if(!key.startsWith(prefix)) return;
            this.chart.removeSeries(this.series[key]);
            delete this.series[key];
        });

    }

}

window.Indicators = new IndicatorEngine(window.ChartEngine);

/*
Python Examples

window.Indicators.setEMA(
20,
[
 {time:1719993600,value:24510},
 {time:1719993900,value:24515}
]
);

window.Indicators.setVWAP(vwapData);

window.Indicators.remove("EMA_20");

window.Indicators.clear();

*/
