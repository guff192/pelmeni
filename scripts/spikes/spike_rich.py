"""Prototype script evaluating inline terminal rendering via Rich in tmux."""

from __future__ import annotations

import sys
import time
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

SAMPLE_THINKING = (
    "Analyzing the request. We need to evaluate Rich for terminal REPL.\n"
    "Step 1: Check inline stdout streaming behaviour.\n"
    "Step 2: Verify in-place line replacement (using Live display).\n"
    "Step 3: Check scrollback preservation in tmux copy-mode.\n"
    "Conclusion: Rich writes sequentially to standard stdout."
)

SAMPLE_MARKDOWN = """
### Assistant Response (Rich Rendering)

Here is a quick demonstration of inline markdown rendering:

```python
def greet(name: str) -> str:
    \"\"\"Return a greeting message.\"\"\"
    return f"Hello, {name}!"
```

- **Feature 1**: Inline streaming directly to terminal scrollback.
- **Feature 2**: Standard tmux mouse scroll and native copy-paste work out of the box.
- **Feature 3**: ANSI styling without hijacking the alternate screen buffer (`smcup`/`rmcup`).
"""


def run_rich_prototype() -> None:
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]Rich Inline REPL Spike[/bold cyan]\n"
            "[dim]Evaluating inline streaming, live line replacement & tmux ergonomics[/dim]",
            border_style="cyan",
        )
    )

    console.print(
        "\n[bold yellow]Stage 1: Streaming Thinking Block (dimmed)[/bold yellow]"
    )
    for char in SAMPLE_THINKING:
        console.print(f"[dim]{char}[/dim]", end="")
        sys.stdout.flush()
        time.sleep(0.01)
    console.print(
        "\n[green]✓ Thinking completed and committed to scrollback.[/green]\n"
    )

    console.print(
        "[bold yellow]Stage 2: Live In-place Tool Status Replacement[/bold yellow]"
    )
    with Live(console=console, refresh_per_second=10) as live:
        for step in range(1, 21):
            table = Table.grid(padding=(0, 1))
            spinner = Spinner("dots", style="cyan")
            table.add_row(
                spinner,
                Text(
                    f"▶ tool: bash 'pytest -q tests/' [running... {step * 5}%]",
                    style="bold blue",
                ),
            )
            live.update(table)
            time.sleep(0.05)

        summary = Text.assemble(
            ("✓ ", "bold green"),
            ("tool: bash (0.42s, exit 0) ", "bold white"),
            ("[output: 280 passed in 1.73s]", "dim italic"),
        )
        live.update(summary)

    console.print(
        "\n[bold yellow]Stage 3: Streaming Markdown Response[/bold yellow]"
    )
    console.print(Markdown(SAMPLE_MARKDOWN))

    console.print(
        Panel(
            "[bold green]Rich Spike Finished[/bold green]\n"
            "Notice: Text is in your normal tmux scrollback buffer.\n"
            "You can use tmux copy mode (Prefix + [), mouse select, and normal scrolling.",
            border_style="green",
        )
    )


if __name__ == "__main__":
    run_rich_prototype()
