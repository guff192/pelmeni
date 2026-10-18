"""Prototype script evaluating full-screen app layout via Textual in tmux."""

from __future__ import annotations

import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, ScrollableContainer, Vertical
from textual.widgets import (
    Collapsible,
    Footer,
    Header,
    LoadingIndicator,
    Markdown,
    Static,
)

SAMPLE_THINKING = (
    "Analyzing the request inside Textual App.\n"
    "Step 1: Check full-screen alternate screen (smcup/rmcup) impact.\n"
    "Step 2: Inspect collapsible container interaction.\n"
    "Step 3: Check tmux scrollback and mouse capture behaviour."
)

SAMPLE_MARKDOWN = """
### Assistant Response (Textual Rendering)

Here is a quick demonstration of Textual layout rendering:

```python
def greet(name: str) -> str:
    \"\"\"Return a greeting message.\"\"\"
    return f"Hello, {name}!"
```

- **Feature 1**: Dedicated widgets and layout panes.
- **Feature 2**: Collapsible thinking container widget.
- **Feature 3**: Internal virtual scrolling (intercepts mouse events).
"""


class TextualSpikeApp(App[None]):
    """Textual interactive spike app."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-scroll {
        height: 1fr;
        border: solid cyan;
        padding: 1;
    }
    #thinking-box {
        margin: 1 0;
        background: $surface;
    }
    #tool-box {
        margin: 1 0;
        padding: 0 1;
        border: heavy blue;
    }
    #response-box {
        margin: 1 0;
    }
    .status-text {
        color: yellow;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit Spike"),
        ("t", "toggle_thinking", "Toggle Thinking"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with ScrollableContainer(id="main-scroll"):
            with Collapsible(
                title="Thinking Block (Click or press 't' to toggle)",
                id="thinking-box",
            ):
                yield Static(SAMPLE_THINKING, id="thinking-content")
            with Container(id="tool-box"):
                yield Static(
                    "▶ tool: bash 'pytest -q tests/' [running...]",
                    id="tool-status",
                    classes="status-text",
                )
                yield LoadingIndicator(id="tool-spinner")
            with Vertical(id="response-box"):
                yield Markdown(SAMPLE_MARKDOWN, id="markdown-response")
        yield Footer()

    async def on_mount(self) -> None:
        """Simulate async tool finish."""
        asyncio.create_task(self._simulate_tool())

    async def _simulate_tool(self) -> None:
        await asyncio.sleep(2)
        tool_status = self.query_one("#tool-status", Static)
        tool_status.update(
            "✓ tool: bash (0.42s, exit 0) [output: 280 passed in 1.73s]"
        )
        tool_status.styles.color = "green"
        tool_spinner = self.query_one("#tool-spinner", LoadingIndicator)
        tool_spinner.display = False

    def action_toggle_thinking(self) -> None:
        collapsible = self.query_one("#thinking-box", Collapsible)
        collapsible.collapsed = not collapsible.collapsed


def run_textual_prototype() -> None:
    app = TextualSpikeApp()
    app.run()


if __name__ == "__main__":
    run_textual_prototype()
