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

        this.telegramButton = document.getElementById("telegramScreenshot");
        this.telegramStatus = document.getElementById("telegramStatus");

        this.registerEvents();
        this.registerTelegramScreenshot();
        this.setActive("cursor");
    }

    registerTelegramScreenshot() {

        if (!this.telegramButton) return;

        this.telegramButton.addEventListener("click", async () => {
            const recipients = window.TelegramPhotoRecipients || [];
            if (!recipients.length) {
                this.setTelegramStatus("Telegram not configured", true);
                return;
            }

            this.telegramButton.disabled = true;
            this.setTelegramStatus("Preparing...");
            const html2canvas = await this.waitForScreenshotLibrary();
            if (!html2canvas) {
                this.setTelegramStatus("Screenshot library unavailable", true);
                this.telegramButton.disabled = false;
                return;
            }

            this.setTelegramStatus("Sending...");
            try {
                const target = document.getElementById("terminal");
                if (!target) throw new Error("Chart container not found");

                const canvas = await html2canvas(target, {
                    backgroundColor: "#ffffff",
                    scale: 2,
                    useCORS: true,
                    logging: false
                });
                const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
                if (!blob) throw new Error("Could not create chart image");

                const symbol = document.getElementById("symbol")?.textContent || "Chart";
                const timeframe = document.getElementById("timeframe")?.textContent || "";
                let sent = 0;
                for (const recipient of recipients) {
                    const form = new FormData();
                    form.append("chat_id", recipient.chat_id);
                    form.append("caption", `${symbol} | ${timeframe}`);
                    form.append("photo", blob, "option-terminal-chart.png");
                    await fetch(`https://api.telegram.org/bot${recipient.token}/sendPhoto`, {
                        method: "POST",
                        mode: "no-cors",
                        body: form
                    });
                    sent += 1;
                }
                if (!sent) throw new Error("Telegram request failed");
                this.setTelegramStatus(`Sent request to ${sent} chat${sent === 1 ? "" : "s"}`);
            } catch (error) {
                this.setTelegramStatus(error.message || "Send failed", true);
            } finally {
                this.telegramButton.disabled = false;
            }
        });
    }

    waitForScreenshotLibrary() {
        return new Promise(resolve => {
            if (window.html2canvas) {
                resolve(window.html2canvas);
                return;
            }

            let checks = 0;
            const timer = setInterval(() => {
                checks += 1;
                if (window.html2canvas) {
                    clearInterval(timer);
                    resolve(window.html2canvas);
                } else if (checks >= 20) {
                    clearInterval(timer);
                    resolve(null);
                }
            }, 150);
        });
    }

    setTelegramStatus(message, isError = false) {
        if (!this.telegramStatus) return;
        this.telegramStatus.textContent = message;
        this.telegramStatus.style.color = isError ? "#dc2626" : "#64748b";
        setTimeout(() => {
            if (this.telegramStatus) this.telegramStatus.textContent = "";
        }, 5000);
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
