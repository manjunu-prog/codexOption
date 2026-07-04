/*
=========================================================
Option Terminal Pro
chart/chart.js
Version: 0.1
=========================================================
*/

class ChartEngine {

    constructor(containerId="chart") {

        this.container = document.getElementById(containerId);

        this.chart = null;
        this.candleSeries = null;
        this.volumeSeries = null;
        this.lastCandles = [];
        this.markerSources = {};
        this.storageKey = "OptionTerminal:v2:chart";
        this.pendingView = null;

        this.init();

    }

    init() {

        this.chart = LightweightCharts.createChart(this.container, {

            width: this.container.clientWidth || 1200,
            height: 700,

            layout: {
                background: {
                    type: "solid",
                    color: "#ffffff"
                },
                textColor: "#334155"
            },

            grid: {
                vertLines: {
                    color: "#eef2f7"
                },
                horzLines: {
                    color: "#eef2f7"
                }
            },

            rightPriceScale: {
                borderColor: "#cbd5e1",
                autoScale: true
            },

            timeScale: {
                borderColor: "#cbd5e1",
                timeVisible: true,
                rightOffset: 8,
                fixLeftEdge: false,
                fixRightEdge: false,
                lockVisibleTimeRangeOnResize: false
            },

            handleScroll: {
                mouseWheel: true,
                pressedMouseMove: true,
                horzTouchDrag: true,
                vertTouchDrag: true
            },

            handleScale: {
                axisPressedMouseMove: true,
                mouseWheel: true,
                pinch: true
            }

        });

        this.candleSeries = this.chart.addCandlestickSeries({

            upColor:"#26a69a",
            downColor:"#ef5350",

            borderUpColor:"#26a69a",
            borderDownColor:"#ef5350",

            wickUpColor:"#26a69a",
            wickDownColor:"#ef5350"

        });

        this.volumeSeries = this.chart.addHistogramSeries({

            priceScaleId:"",
            priceFormat:{
                type:"volume"
            }

        });

        this.volumeSeries.priceScale().applyOptions({

            scaleMargins:{

                top:0.80,
                bottom:0

            }

        });

        window.addEventListener("resize",()=>{

            this.chart.applyOptions({

                width:this.container.clientWidth

            });

        });

        this.installAxisPan();

        this.chart.subscribeCrosshairMove((param)=>{

            if(!param.point) return;

            const d = param.seriesData.get(this.candleSeries);

            if(!d) return;

            const el=document.getElementById("ohlc");

            if(el){

                el.innerHTML=
                    `O:${d.open}
                     H:${d.high}
                     L:${d.low}
                     C:${d.close}`;

            }

        });

        this.chart.subscribeClick((param)=>{
            const tool = window.Toolbar ? window.Toolbar.getTool() : "cursor";
            if(tool !== "cursor" || param.time == null) return;
            const index = this.lastCandles.findIndex(candle => String(candle.time) === String(param.time));
            if(index < 0) return;
            const halfWindow = Math.min(90, Math.max(45, Math.floor(this.lastCandles.length / 4)));
            const range = {
                from: Math.max(index - halfWindow, -10),
                to: Math.min(index + halfWindow, this.lastCandles.length + 10)
            };
            this.chart.timeScale().setVisibleLogicalRange(range);
            this.storeView({time: range});
        });

        this.chart.timeScale().subscribeVisibleLogicalRangeChange((range)=>{
            if(!range || !this.storageKey) return;
            this.storeView({time: range});
        });

        const priceScale = this.chart.priceScale("right");
        if(priceScale && priceScale.subscribeVisiblePriceRangeChange){
            priceScale.subscribeVisiblePriceRangeChange((range)=>{
                if(!range || !this.storageKey) return;
                this.storeView({price: {from: range.from, to: range.to}});
            });
        }

    }

    installAxisPan(){

        const panTargets = [
            document.getElementById("statusBar"),
            this.container
        ].filter(Boolean);

        panTargets.forEach(target=>{
            let dragging = false;
            let startX = 0;
            let startRange = null;

            target.addEventListener("pointerdown",(event)=>{
                const rect = target.getBoundingClientRect();
                const isStatus = target.id === "statusBar";
                const isBottomBand = event.clientY > rect.bottom - 42;
                if(!isStatus && !isBottomBand) return;

                dragging = true;
                startX = event.clientX;
                startRange = this.chart.timeScale().getVisibleLogicalRange();
                target.setPointerCapture(event.pointerId);
                event.preventDefault();
            });

            target.addEventListener("pointermove",(event)=>{
                if(!dragging || !startRange) return;
                const width = Math.max(this.container.clientWidth, 1);
                const visibleBars = startRange.to - startRange.from;
                const barsPerPixel = visibleBars / width;
                const deltaBars = (event.clientX - startX) * barsPerPixel;
                const range = {
                    from: startRange.from - deltaBars,
                    to: startRange.to - deltaBars
                };
                this.chart.timeScale().setVisibleLogicalRange(range);
                this.storeView({time: range});
                event.preventDefault();
            });

            const stop = (event)=>{
                if(!dragging) return;
                dragging = false;
                startRange = null;
                try{ target.releasePointerCapture(event.pointerId); }catch(e){}
            };

            target.addEventListener("pointerup", stop);
            target.addEventListener("pointercancel", stop);
        });

    }

    setCandles(data){

        const cleanData = (data || []).filter(item =>
            item &&
            item.time != null &&
            Number.isFinite(item.open) &&
            Number.isFinite(item.high) &&
            Number.isFinite(item.low) &&
            Number.isFinite(item.close)
        );

        this.lastCandles = cleanData;
        const view = this.readStoredView();
        this.candleSeries.setData(cleanData);
        if(!this.applyView(view)){
            this.showRecentSession();
        }else{
            this.pendingView = view;
            setTimeout(()=>this.applyView(this.pendingView), 0);
            setTimeout(()=>this.applyView(this.pendingView), 120);
        }

    }

    showRecentSession(){

        if(!this.lastCandles || this.lastCandles.length === 0){
            this.chart.timeScale().fitContent();
            return;
        }

        const last = this.lastCandles[this.lastCandles.length - 1];
        const lastDate = new Date(Number(last.time) * 1000).toDateString();
        let firstIndex = this.lastCandles.findIndex(candle =>
            new Date(Number(candle.time) * 1000).toDateString() === lastDate
        );
        if(firstIndex < 0){
            firstIndex = Math.max(0, this.lastCandles.length - 120);
        }
        const range = {
            from: Math.max(firstIndex - 8, -10),
            to: this.lastCandles.length + 8
        };
        this.chart.timeScale().setVisibleLogicalRange(range);
        this.storeView({time: range});

    }

    readStoredView(){

        if(!this.storageKey) return false;
        try{
            const raw = this.readStorage(this.storageKey);
            if(!raw) return false;
            const view = JSON.parse(raw);
            if(view && view.time && Number.isFinite(view.time.from) && Number.isFinite(view.time.to)) return view;
            if(view && Number.isFinite(view.from) && Number.isFinite(view.to)) return {time: view};
            return false;
        }catch(e){
            return false;
        }

    }

    storeView(view){

        const current = this.readStoredView() || {};
        const payload = JSON.stringify({
            time: view.time || current.time,
            price: view.price || current.price
        });
        try{ window.localStorage.setItem(this.storageKey, payload); }catch(e){}
        try{ window.sessionStorage.setItem(this.storageKey, payload); }catch(e){}
        try{ window.parent.localStorage.setItem(this.storageKey, payload); }catch(e){}
        try{ window.parent.sessionStorage.setItem(this.storageKey, payload); }catch(e){}

    }

    readStorage(key){

        const readers = [
            ()=>window.localStorage.getItem(key),
            ()=>window.sessionStorage.getItem(key),
            ()=>window.parent.localStorage.getItem(key),
            ()=>window.parent.sessionStorage.getItem(key)
        ];
        for(const read of readers){
            try{
                const value = read();
                if(value) return value;
            }catch(e){}
        }
        return null;

    }

    applyView(view){

        if(!view || !view.time || !Number.isFinite(view.time.from) || !Number.isFinite(view.time.to)) return false;
        try{
            this.chart.timeScale().setVisibleLogicalRange(view.time);
            const priceScale = this.chart.priceScale("right");
            if(
                view.price &&
                Number.isFinite(view.price.from) &&
                Number.isFinite(view.price.to) &&
                priceScale &&
                priceScale.setVisibleRange
            ){
                priceScale.setVisibleRange(view.price);
            }
            return true;
        }catch(e){
            return false;
        }

    }

    setVolume(data){

        const cleanData = (data || []).filter(item =>
            item &&
            item.time != null &&
            Number.isFinite(item.value)
        );

        this.volumeSeries.setData(cleanData);

    }

    update(candle){

        this.candleSeries.update(candle);

    }

    updateVolume(bar){

        this.volumeSeries.update(bar);

    }

    setMarkers(markers){

        this.setMarkerSource("default", markers || []);

    }

    setMarkerSource(name, markers){

        this.markerSources[name || "default"] = markers || [];
        const merged = Object.values(this.markerSources).flat();
        merged.sort((a,b)=>(Number(a.time) || 0) - (Number(b.time) || 0));
        this.candleSeries.setMarkers(merged);

    }

    setMeta(symbol,timeframe,chartId){

        const symbolEl = document.getElementById("symbol");
        const timeframeEl = document.getElementById("timeframe");
        if(symbolEl) symbolEl.textContent = symbol || "";
        if(timeframeEl) timeframeEl.textContent = timeframe || "";
        this.storageKey = `OptionTerminal:v2:chart:${chartId || symbol || "symbol"}:${timeframe || "tf"}`;

    }

    preserveView(){

        const view = this.pendingView || this.readStoredView();
        if(this.applyView(view)){
            this.pendingView = view;
        }

    }

    clear(){

        this.candleSeries.setData([]);
        this.volumeSeries.setData([]);

    }

}

/* Global instance */

window.ChartEngine = new ChartEngine();

/*
Python Example:

window.ChartEngine.setCandles(candles)
window.ChartEngine.setVolume(volume)
*/
