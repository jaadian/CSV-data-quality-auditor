from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from csv_auditor.models import AuditResult


def render_html_report(audit_result: AuditResult, output_path: str | Path | None = None) -> str:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )

    template = env.get_template("report.html.j2")
    rendered = template.render(result=audit_result)

    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")

    return rendered
