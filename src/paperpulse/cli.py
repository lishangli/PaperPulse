"""PaperPulse CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from . import __version__
from .config import PaperPulseConfig, find_config_file, load_config
from .storage.database import Database


@click.group()
@click.version_option(version=__version__)
@click.option("--config", "-c", "config_path", type=click.Path(), help="Config file path")
@click.pass_context
def main(ctx: click.Context, config_path: Optional[str]):
    """PaperPulse - Paper monitoring and IDEA recommendation system."""
    # Load config
    if config_path:
        config = PaperPulseConfig.load(config_path)
    else:
        config = load_config()

    ctx.ensure_object(dict)
    ctx.obj["config"] = config

    # Initialize database
    db = Database(config.storage.database)
    ctx.obj["db"] = db


@main.command()
@click.pass_context
def monitor(ctx: click.Context):
    """Run paper monitoring once."""
    from .integration.scheduler import run_once

    config = ctx.obj["config"]
    results = run_once(config)

    click.echo("\n✅ Monitoring complete!")
    click.echo(f"  Papers collected: {results.get('papers_collected', 0)}")
    click.echo(f"  Papers downloaded: {results.get('papers_downloaded', 0)}")
    click.echo(f"  Papers converted: {results.get('papers_converted', 0)}")
    click.echo(f"  Papers analyzed: {results.get('papers_analyzed', 0)}")
    click.echo(f"  Ideas generated: {results.get('ideas_generated', 0)}")

    if results.get("report_path"):
        click.echo(f"\n📄 Report: {results['report_path']}")


@main.command()
@click.option("--days", "-d", default=1, help="Days to look back")
@click.option("--limit", "-l", default=50, help="Maximum papers to collect")
@click.pass_context
def collect(ctx: click.Context, days: int, limit: int):
    """Collect papers from sources."""
    from .collectors.arxiv import ArxivCollector
    from .collectors.semantic_scholar import SemanticScholarCollector
    from .collectors.papers_with_code import PapersWithCodeCollector

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    papers = []

    # arXiv
    if config.sources.arxiv.enabled:
        click.echo("📥 Collecting from arXiv...")
        collector = ArxivCollector(
            categories=config.sources.arxiv.categories,
            keywords=config.sources.arxiv.keywords,
            max_papers=limit,
        )
        arxiv_papers = collector.get_recent(days=days)
        papers.extend(arxiv_papers)
        click.echo(f"   Found {len(arxiv_papers)} papers")

    # Semantic Scholar
    if config.sources.semantic_scholar.enabled:
        click.echo("📥 Collecting from Semantic Scholar...")
        collector = SemanticScholarCollector(
            fields=config.sources.semantic_scholar.fields,
            max_papers=min(limit, config.sources.semantic_scholar.max_papers_per_day),
        )
        s2_papers = collector.get_recent(days=days)
        papers.extend(s2_papers)
        click.echo(f"   Found {len(s2_papers)} papers")

    # Papers with Code
    if config.sources.papers_with_code.enabled:
        click.echo("📥 Collecting from Papers with Code...")
        collector = PapersWithCodeCollector(
            areas=config.sources.papers_with_code.areas,
            max_papers=min(limit, config.sources.papers_with_code.max_papers_per_day),
        )
        pwc_papers = collector.get_recent(days=days)
        papers.extend(pwc_papers)
        click.echo(f"   Found {len(pwc_papers)} papers")

    # Save to database
    if papers:
        db.insert_papers(papers)
        click.echo(f"\n✅ Saved {len(papers)} papers to database")
    else:
        click.echo("\n⚠️ No papers found")


@main.command()
@click.argument("paper_ids", nargs=-1)
@click.option("--latex", is_flag=True, help="Download LaTeX source")
@click.option("--pdf", is_flag=True, default=True, help="Download PDF")
@click.pass_context
def download(ctx: click.Context, paper_ids: list[str], latex: bool, pdf: bool):
    """Download documents for papers."""
    from .collectors.arxiv import ArxivCollector
    from .downloader.pdf import DocumentDownloader

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    downloader = DocumentDownloader(config, db)
    arxiv_collector = ArxivCollector()

    if not paper_ids:
        # Download pending papers
        papers = db.get_papers(limit=20)
    else:
        # Download specific papers
        papers = []
        for pid in paper_ids:
            paper = db.get_paper(pid)
            if paper:
                papers.append(paper)
            elif pid.startswith("arxiv-") or len(pid.split(".")) == 2:
                # arXiv ID
                arxiv_id = pid.replace("arxiv-", "")
                paper = arxiv_collector.get_paper_by_id(arxiv_id)
                if paper:
                    papers.append(paper)

    if not papers:
        click.echo("No papers to download")
        return

    click.echo(f"📥 Downloading {len(papers)} papers...")

    success_count = 0
    for paper in papers:
        click.echo(f"   {paper.arxiv_id or paper.paper_id}...", nl=False)

        if pdf and paper.arxiv_id:
            success, path = downloader.download_arxiv_pdf(paper.arxiv_id)
            if success:
                paper.pdf_path = path
                success_count += 1
                click.echo(f" ✅ PDF")
            else:
                click.echo(f" ❌ {path}")

        if latex and paper.arxiv_id:
            success, path = downloader.download_latex(paper.arxiv_id)
            if success:
                paper.latex_path = path
                click.echo(f"       LaTeX: ✅")

        db.update_paper(paper)

    click.echo(f"\n✅ Downloaded {success_count}/{len(papers)} documents")


@main.command()
@click.argument("paper_ids", nargs=-1)
@click.pass_context
def convert(ctx: click.Context, paper_ids: list[str]):
    """Convert PDFs to Markdown."""
    from .converter.mineru import MinerUConverter

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    converter = MinerUConverter(config.storage.markdown_dir)

    if not converter.is_available():
        click.echo("❌ MinerU not installed")
        click.echo("\nInstall with: pip install mineru[all]")
        return

    if not paper_ids:
        # Convert pending papers
        papers = [p for p in db.get_papers(limit=20) if p.pdf_path and not p.markdown_path]
    else:
        papers = []
        for pid in paper_ids:
            paper = db.get_paper(pid)
            if paper and paper.pdf_path:
                papers.append(paper)

    if not papers:
        click.echo("No PDFs to convert")
        return

    click.echo(f"📄 Converting {len(papers)} PDFs...")

    success_count = 0
    for paper in papers:
        click.echo(f"   {paper.arxiv_id or paper.paper_id}...", nl=False)

        success, result = converter.convert(paper.pdf_path)

        if success:
            paper.markdown_path = result
            db.update_paper(paper)
            success_count += 1
            click.echo(" ✅")
        else:
            click.echo(f" ❌ {result}")

    click.echo(f"\n✅ Converted {success_count}/{len(papers)} PDFs")


@main.command()
@click.argument("paper_ids", nargs=-1)
@click.pass_context
def analyze(ctx: click.Context, paper_ids: list[str]):
    """Analyze papers using LLM."""
    from .analysis.llm_client import create_llm_client
    from .analysis.paper_analyzer import PaperAnalyzer

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Check API key
    api_key = config.llm.get_api_key()
    if not api_key:
        click.echo("❌ No API key configured")
        click.echo(f"   Set {config.llm.api_key_env} environment variable")
        return

    # Get papers
    if not paper_ids:
        papers = db.get_papers(limit=20)
        papers = [p for p in papers if p.markdown_path or p.abstract]
    else:
        papers = []
        for pid in paper_ids:
            paper = db.get_paper(pid)
            if paper:
                papers.append(paper)

    if not papers:
        click.echo("No papers to analyze")
        return

    click.echo(f"🤖 Analyzing {len(papers)} papers...")

    llm = create_llm_client(config.llm)
    analyzer = PaperAnalyzer(llm, db)

    success_count = 0
    for i, paper in enumerate(papers, 1):
        click.echo(f"   [{i}/{len(papers)}] {paper.arxiv_id or paper.paper_id}...", nl=False)

        success = analyzer.analyze_paper(paper)

        if success:
            success_count += 1
            click.echo(" ✅")
        else:
            click.echo(" ❌")

    click.echo(f"\n✅ Analyzed {success_count}/{len(papers)} papers")


@main.command()
@click.option("--num", "-n", default=5, help="Number of ideas to generate")
@click.pass_context
def ideas(ctx: click.Context, num: int):
    """Generate research ideas."""
    from .analysis.llm_client import create_llm_client
    from .ideas.generator import IdeaGenerator

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Check API key
    api_key = config.llm.get_api_key()
    if not api_key:
        click.echo("❌ No API key configured")
        return

    # Get analyzed papers
    papers = db.get_papers(limit=30)
    analyzed = [p for p in papers if p.keywords or p.innovations]

    if len(analyzed) < 3:
        click.echo("⚠️ Need at least 3 analyzed papers to generate ideas")
        click.echo("   Run: paperpulse analyze")
        return

    click.echo(f"💡 Generating ideas from {len(analyzed)} papers...")

    llm = create_llm_client(config.llm)
    generator = IdeaGenerator(llm, db, config)

    generated = generator.generate_ideas(analyzed, num_ideas=num)

    if generated:
        click.echo(f"\n✅ Generated {len(generated)} ideas:\n")
        for i, idea in enumerate(generated, 1):
            click.echo(f"  #{i} [{idea.score:.2f}] {idea.title}")
    else:
        click.echo("\n⚠️ No ideas generated")


@main.command()
@click.argument("idea_id")
@click.option("--dry-run", is_flag=True, help="Show config without running")
@click.pass_context
def research(ctx: click.Context, idea_id: str, dry_run: bool):
    """Start AutoResearchClaw research for an idea."""
    from .integration.researchclaw import ResearchClawIntegration

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Get idea
    idea = db.get_idea(idea_id)
    if not idea:
        click.echo(f"❌ Idea not found: {idea_id}")
        return

    integration = ResearchClawIntegration(config, db)

    if not integration.is_available():
        click.echo("❌ AutoResearchClaw not available")
        click.echo(f"   Check path: {config.integration.researchclaw.path}")
        return

    if dry_run:
        click.echo(f"Would start research for: {idea.title}")
        click.echo(f"  Related papers: {len(idea.related_paper_ids)}")
        return

    click.echo(f"🚀 Starting research: {idea.title}")

    success, result = integration.start_research(idea)

    if success:
        click.echo(f"✅ Research started: {result}")
    else:
        click.echo(f"❌ Failed: {result}")


@main.command()
@click.option("--daily", is_flag=True, help="Generate daily report")
@click.option("--weekly", is_flag=True, help="Generate weekly report")
@click.pass_context
def report(ctx: click.Context, daily: bool, weekly: bool):
    """Generate reports."""
    from .output.markdown import MarkdownReport

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    reporter = MarkdownReport(db, config.output.reports_dir)

    if daily or not weekly:
        path = reporter.generate_daily_report()
        click.echo(f"✅ Daily report: {path}")

    if weekly:
        path = reporter.generate_weekly_report()
        click.echo(f"✅ Weekly report: {path}")


@main.command()
@click.pass_context
def obsidian(ctx: click.Context):
    """Sync papers and ideas to Obsidian."""
    from .output.obsidian import ObsidianWriter

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    if not config.obsidian.enabled:
        click.echo("❌ Obsidian integration disabled in config")
        return

    writer = ObsidianWriter(config, db)

    # Sync papers
    papers = db.get_recent_papers(days=7)
    if papers:
        click.echo(f"📚 Syncing {len(papers)} papers...")
        paths = writer.sync_papers(papers)
        click.echo(f"   Synced: {len(paths)}")

    # Sync ideas
    ideas = db.get_top_ideas(limit=20)
    if ideas:
        click.echo(f"💡 Syncing {len(ideas)} ideas...")
        paths = writer.sync_ideas(ideas)
        click.echo(f"   Synced: {len(paths)}")

    click.echo("\n✅ Sync complete")


@main.command()
@click.pass_context
def trends(ctx: click.Context):
    """Show trending keywords."""
    from .analysis.trend_detector import TrendDetector

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    detector = TrendDetector(db)
    trends = detector.detect_trends(days=7)

    if not trends:
        click.echo("No trend data available. Run analysis first.")
        return

    click.echo("🔥 Trending Keywords (last 7 days):\n")
    click.echo(f"{'Keyword':<30} {'Count':>8} {'Trend':>10}")
    click.echo("-" * 50)

    for t in trends:
        trend_str = f"↑ {t.trend_percent}%" if t.trend_percent > 0 else f"↓ {abs(t.trend_percent)}%"
        click.echo(f"{t.keyword:<30} {t.count:>8} {trend_str:>10}")


@main.command()
@click.pass_context
def db(ctx: click.Context):
    """Show database statistics."""
    db = ctx.obj["db"]

    stats = db.get_stats()

    click.echo("📊 Database Statistics\n")
    click.echo(f"  Total papers:      {stats.get('total_papers', 0)}")
    click.echo(f"  Downloaded:        {stats.get('downloaded_papers', 0)}")
    click.echo(f"  Analyzed:          {stats.get('analyzed_papers', 0)}")
    click.echo(f"  Papers today:      {stats.get('papers_today', 0)}")
    click.echo(f"  Total ideas:       {stats.get('total_ideas', 0)}")
    click.echo(f"  Researched ideas:  {stats.get('researched_ideas', 0)}")


@main.command()
@click.pass_context
def doctor(ctx: click.Context):
    """Check environment and configuration."""
    config = ctx.obj["config"]

    click.echo("📋 PaperPulse Doctor\n")

    # Config
    click.echo("✓ Configuration loaded")

    # Database
    try:
        db = Database(config.storage.database)
        stats = db.get_stats()
        click.echo(f"✓ Database: {stats.get('total_papers', 0)} papers")
    except Exception as e:
        click.echo(f"✗ Database: {e}")

    # LLM
    api_key = config.llm.get_api_key()
    if api_key:
        click.echo(f"✓ API key: {config.llm.api_key_env} is set")
    else:
        click.echo(f"✗ API key: {config.llm.api_key_env} not set")

    # MinerU
    try:
        from .converter.mineru import MinerUConverter
        converter = MinerUConverter(config.storage.markdown_dir)
        if converter.is_available():
            click.echo("✓ MinerU: installed")
        else:
            click.echo("○ MinerU: not installed (optional)")
    except:
        click.echo("○ MinerU: not installed (optional)")

    # Obsidian
    if config.obsidian.vault_path:
        vault = Path(config.obsidian.vault_path)
        if vault.exists():
            click.echo(f"✓ Obsidian vault: {vault}")
        else:
            click.echo(f"✗ Obsidian vault: {vault} (not found)")
    else:
        click.echo("○ Obsidian: using default directory")

    # AutoResearchClaw
    rc_path = Path(config.integration.researchclaw.path)
    cli_path = Path(config.integration.researchclaw.venv_path) / "bin" / "researchclaw"
    if cli_path.exists():
        click.echo(f"✓ AutoResearchClaw: available")
    else:
        click.echo(f"○ AutoResearchClaw: not found at {cli_path}")


@main.command()
@click.option("--daemon", is_flag=True, help="Run as daemon")
@click.pass_context
def daemon_cmd(ctx: click.Context, daemon: bool):
    """Start the scheduler daemon."""
    from .integration.scheduler import PaperPulseScheduler

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    scheduler = PaperPulseScheduler(config, db)

    if daemon:
        click.echo("Starting PaperPulse daemon...")
        scheduler.start()
    else:
        click.echo("Running once...")
        from .integration.scheduler import run_once
        run_once(config)


if __name__ == "__main__":
    main()