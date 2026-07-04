/*
=========================================================
Option Terminal Pro
toolbar.js
=========================================================
*/

class Toolbar {

    constructor() {

        this.activeTool = "cursor";

        this.tools = {
            cursor: document.getElementById("cursorTool"),
            crosshair: document.getElementById("crosshairTool"),
            trend: document.getElementById("trendTool"),
            horizontal: document.getElementById("horizontalTool"),
            vertical: document.getElementById("verticalTool"),
            rectangle: document.getElementById("rectangleTool"),
            fib: document.getElementById("fibTool"),
            text: document.getElementById("textTool"),
            delete: document.getElementById("deleteTool")
        };

        this.registerEvents();
        this.setActive("cursor");
    }

    registerEvents() {

        Object.keys(this.tools).forEach(name => {

            const btn = this.tools[name];

            if (!btn) return;

            btn.addEventListener("click", () => {
                this.setActive(name);
            });

        });

        document.addEventListener("keydown", (e) => {

            switch (e.key.toLowerCase()) {

                case "v":
                    this.setActive("cursor");
                    break;

                case "h":
                    this.setActive("horizontal");
                    break;

                case "r":
                    this.setActive("rectangle");
                    break;

                case "t":
                    this.setActive("trend");
                    break;

                case "c":
                    this.setActive("crosshair");
                    break;

                case "delete":
                case "backspace":
                    document.dispatchEvent(new CustomEvent("deleteDrawing"));
                    break;
            }

        });

    }

    setActive(tool) {

        this.activeTool = tool;

        Object.values(this.tools).forEach(btn => {
            if (btn) btn.classList.remove("active");
        });

        if (this.tools[tool]) {
            this.tools[tool].classList.add("active");
        }

        console.log("Active Tool:", tool);

        // Notify other modules
        document.dispatchEvent(
            new CustomEvent("toolChanged", {
                detail: {
                    tool: tool
                }
            })
        );

    }

    getTool() {
        return this.activeTool;
    }

}

window.Toolbar = new Toolbar();

/*
Other modules can listen like:

document.addEventListener("toolChanged",(e)=>{
    console.log(e.detail.tool);
});

*/
