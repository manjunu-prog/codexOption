/*
=========================================================
Option Terminal Pro
drawings.js
Version 0.1
=========================================================
Basic drawing framework.
Future versions will add drag/resize/save/load.
=========================================================
*/

class DrawingEngine {

    constructor(chartEngine){

        this.chartEngine = chartEngine;
        this.chart = chartEngine.chart;

        this.activeTool = "cursor";

        this.horizontalLines = [];
        this.verticalLines = [];
        this.markers = [];
        this.actions = [];

        this.registerEvents();

    }

    registerEvents(){

        document.addEventListener("toolChanged",(e)=>{
            this.activeTool = e.detail.tool;
            console.log("Drawing Tool:",this.activeTool);
        });

        document.addEventListener("deleteDrawing",()=>{
            this.deleteLast();
        });

        this.chart.subscribeClick((param)=>{

            if(!param.point) return;

            switch(this.activeTool){

                case "horizontal":
                    this.addHorizontalLine(param.seriesData);
                    break;

                case "vertical":
                    this.addVerticalMarker(param.time);
                    break;

                case "text":
                    this.addText(param.time,param.point.y);
                    break;

                case "delete":
                    this.deleteLast();
                    break;

                default:
                    break;
            }

        });

    }

    addHorizontalLine(seriesData){

        const candle = seriesData.get(this.chartEngine.candleSeries);

        if(!candle) return;

        const line = this.chartEngine.candleSeries.createPriceLine({

            price:candle.close,
            color:"#ff9800",
            lineWidth:2,
            lineStyle:2,
            axisLabelVisible:true,
            title:"H-Line"

        });

        this.horizontalLines.push(line);
        this.actions.push({type:"priceLine", item:line});

    }

    addVerticalMarker(time){

        this.markers.push({

            time:time,
            position:"aboveBar",
            color:"#2196f3",
            shape:"circle",
            text:"V"

        });

        this.actions.push({type:"marker"});
        this.applyDrawingMarkers();

    }

    addText(time,y){

        const txt = prompt("Enter Label");

        if(!txt) return;

        this.markers.push({

            time:time,
            position:"aboveBar",
            color:"#ffffff",
            shape:"square",
            text:txt

        });

        this.actions.push({type:"marker"});
        this.applyDrawingMarkers();

    }

    applyDrawingMarkers(){

        if(this.chartEngine.setMarkerSource){
            this.chartEngine.setMarkerSource("drawings", this.markers);
        }else{
            this.chartEngine.candleSeries.setMarkers(this.markers);
        }

    }

    deleteLast(){

        const action = this.actions.pop();
        if(!action) return;

        if(action.type === "priceLine"){
            this.chartEngine.candleSeries.removePriceLine(action.item);
            this.horizontalLines = this.horizontalLines.filter(line=>line !== action.item);
        }

        if(action.type === "marker"){
            this.markers.pop();
            this.applyDrawingMarkers();
        }

    }

    clear(){

        this.markers=[];

        this.applyDrawingMarkers();

        this.horizontalLines.forEach(l=>{

            this.chartEngine.candleSeries.removePriceLine(l);

        });

        this.horizontalLines=[];
        this.actions=[];

    }

}

window.DrawingEngine = new DrawingEngine(window.ChartEngine);

/*
Future Versions
----------------
✓ Trend Lines
✓ Rectangle
✓ Fib Retracement
✓ Drag & Drop
✓ Resize
✓ Delete Selected
✓ Save Layout
✓ Load Layout
✓ FVG Boxes
✓ Order Blocks
✓ Liquidity Zones
*/
