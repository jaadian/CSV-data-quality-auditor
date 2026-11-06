from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from csv_auditor import __version__
from csv_auditor.config import load_config
from csv_auditor.core.auditor import CsvAuditor
from csv_auditor.exceptions import AuditorError, ConfigError, EncodingError, InputFileError
from csv_auditor.models import AuditResult, Severity
from csv_auditor.reporting.html_report import render_html_report
from csv_auditor.reporting.json_report import generate_json_report

app = typer.Typer(
    name="csv-auditor",
    help="A memory-bounded, schema-aware CSV data quality auditor and profiling engine",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]csv-auditor[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version", callback=version_callback, is_eager=True, help="Show version and exit"
        ),
    ] = None,
) -> None:
    pass


@app.command(name="analyze")
def analyze(
    file: Annotated[Path, typer.Argument(help="Path to CSV dataset to audit", exists=False)],
    config: Annotated[
        Optional[Path], typer.Option("--config", "-c", help="Path to YAML rules configuration file")
    ] = None,
    encoding: Annotated[
        Optional[str], typer.Option("--encoding", "-e", help="Explicit CSV file encoding override")
    ] = None,
    delimiter: Annotated[
        Optional[str],
        typer.Option("--delimiter", "-d", help="Explicit CSV field delimiter override"),
    ] = None,
    out_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Output directory for generated reports")
    ] = Path("./reports"),
    report_format: Annotated[
        str, typer.Option("--format", "-f", help="Report format to generate: json, html, or both")
    ] = "both",
    unique_keys: Annotated[
        Optional[list[str]],
        typer.Option("--unique-key", "-k", help="Column(s) forming a unique composite key"),
    ] = None,
    mask_columns: Annotated[
        Optional[str],
        typer.Option(
            "--mask-columns", "-m", help="Comma-separated column names to mask in reports"
        ),
    ] = None,
    fail_on: Annotated[
        Optional[str],
        typer.Option(
            "--fail-on",
            help="Exit with code 1 if issues meet or exceed severity: low, medium, or high",
        ),
    ] = None,
    max_size_mb: Annotated[
        Optional[float], typer.Option("--max-size-mb", help="Maximum allowable file size in MB")
    ] = None,
    on_bad_rows: Annotated[
        str,
        typer.Option(
            "--on-bad-rows", help="Policy for malformed rows: error (default) or skip (data loss)"
        ),
    ] = "error",
    no_header: Annotated[
        bool, typer.Option("--no-header", help="Treat the first CSV record as data")
    ] = False,
    columns: Annotated[
        Optional[str],
        typer.Option("--columns", help="Comma-separated names for headerless columns"),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable detailed logging output")
    ] = False,
) -> None:
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        err_console.print(f"[bold red]Configuration Error:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    if mask_columns:
        parsed_masks = [c.strip() for c in mask_columns.split(",") if c.strip()]
        cfg.mask_columns.extend(parsed_masks)

    if fail_on:
        try:
            cfg.fail_on = Severity(fail_on.lower())
        except ValueError as exc:
            err_console.print(
                f"[bold red]Invalid --fail-on level:[/bold red] '{fail_on}'. Allowed: low, medium, high"
            )
            raise typer.Exit(code=2) from exc

    formatted_unique_keys: list[list[str]] = []
    if unique_keys:
        for k in unique_keys:
            parts = [p.strip() for p in k.split(",") if p.strip()]
            if parts:
                formatted_unique_keys.append(parts)

    if report_format not in ("json", "html", "both"):
        err_console.print("[red]--format must be json, html, or both[/red]")
        raise typer.Exit(code=2)
    if on_bad_rows not in ("error", "skip"):
        err_console.print("[red]--on-bad-rows must be error or skip[/red]")
        raise typer.Exit(code=2)
    auditor = CsvAuditor(config=cfg)

    try:
        with console.status(f"[cyan]Auditing {file.name}...[/cyan]"):
            result: AuditResult = auditor.audit(
                file_path=file,
                user_encoding=encoding,
                user_delimiter=delimiter,
                unique_keys=formatted_unique_keys,
                on_bad_rows=on_bad_rows,
                max_size_mb=max_size_mb,
                has_header=False if no_header or columns else None,
                custom_columns=[col.strip() for col in columns.split(",")] if columns else None,
            )
    except ConfigError as exc:
        err_console.print(f"[bold red]Configuration Error:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    except InputFileError as exc:
        err_console.print(f"[bold red]Input File Error:[/bold red] {exc}")
        raise typer.Exit(code=3) from exc
    except EncodingError as exc:
        err_console.print(f"[bold red]Encoding Error:[/bold red] {exc}")
        raise typer.Exit(code=3) from exc
    except AuditorError as exc:
        err_console.print(f"[bold red]Audit Error:[/bold red] {exc}")
        raise typer.Exit(code=exc.exit_code) from exc
    except Exception as exc:
        err_console.print(f"[bold red]Unexpected Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    base_stem = file.stem

    if report_format in ("json", "both"):
        json_path = out_dir / f"{base_stem}_audit_report.json"
        json_path.write_text(generate_json_report(result), encoding="utf-8")
        if verbose:
            console.print(f"[green]Saved JSON report to:[/green] {json_path}")

    if report_format in ("html", "both"):
        html_path = out_dir / f"{base_stem}_audit_report.html"
        render_html_report(result, output_path=html_path)
        if verbose:
            console.print(f"[green]Saved HTML report to:[/green] {html_path}")

    _print_summary(result)

    if cfg.fail_on is not None:
        threshold = cfg.fail_on
        has_failure = False
        if threshold == Severity.LOW and (
            result.issue_summary.get("low", 0) > 0
            or result.issue_summary.get("medium", 0) > 0
            or result.issue_summary.get("high", 0) > 0
        ):
            has_failure = True
        elif threshold == Severity.MEDIUM and (
            result.issue_summary.get("medium", 0) > 0 or result.issue_summary.get("high", 0) > 0
        ):
            has_failure = True
        elif threshold == Severity.HIGH and result.issue_summary.get("high", 0) > 0:
            has_failure = True

        if has_failure:
            err_console.print(
                f"[bold red]Audit failed trigger: issues found meeting or exceeding severity '{threshold.value}'[/bold red]"
            )
            raise typer.Exit(code=1)

    raise typer.Exit(code=0)


def _print_summary(result: AuditResult) -> None:
    score = result.score
    meta = result.metadata

    console.print()
    score_color = "green" if score.overall >= 85 else ("yellow" if score.overall >= 60 else "red")
    console.print(
        f"[bold]Data Quality Audit Summary:[/bold] [bold {score_color}]{score.overall:.2f}/100 ({score.rating})[/bold {score_color}]"
    )
    console.print(
        f"File: [cyan]{meta.file_path}[/cyan] | Rows: {meta.total_rows:,} | Columns: {meta.total_columns}"
    )

    summary_table = Table(title="Quality Dimensions", show_header=True, header_style="bold magenta")
    summary_table.add_column("Dimension", style="cyan")
    summary_table.add_column("Score", justify="right")
    summary_table.add_column("Weight Used", justify="right")

    summary_table.add_row(
        "Completeness",
        f"{score.completeness:.2f}%",
        f"{score.weights_used.get('completeness', 0):.2f}",
    )
    summary_table.add_row(
        "Uniqueness", f"{score.uniqueness:.2f}%", f"{score.weights_used.get('uniqueness', 0):.2f}"
    )
    summary_table.add_row(
        "Consistency",
        f"{score.consistency:.2f}%",
        f"{score.weights_used.get('consistency', 0):.2f}",
    )
    if score.validity is not None:
        summary_table.add_row(
            "Validity", f"{score.validity:.2f}%", f"{score.weights_used.get('validity', 0):.2f}"
        )
    else:
        summary_table.add_row("Validity", "N/A (no rules)", "-")

    console.print(summary_table)

    issues_table = Table(title="Issues Summary", show_header=True, header_style="bold red")
    issues_table.add_column("Severity")
    issues_table.add_column("Count", justify="right")
    issues_table.add_row("[red]High[/red]", str(result.issue_summary.get("high", 0)))
    issues_table.add_row("[yellow]Medium[/yellow]", str(result.issue_summary.get("medium", 0)))
    issues_table.add_row("[cyan]Low[/cyan]", str(result.issue_summary.get("low", 0)))
    console.print(issues_table)
    console.print()


if __name__ == "__main__":
    app()
