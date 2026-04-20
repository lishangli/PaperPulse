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
@click.option("--mode", "-m", default="auto", help="Conversion mode: auto (LaTeX if arXiv), latex (force LaTeX), pymupdf (force PyMuPDF)")
@click.option("--pdf-dir", "-p", default="data/pdfs", help="PDF directory for PyMuPDF fallback")
@click.option("--batch", "-b", is_flag=True, help="Convert all pending papers")
@click.pass_context
def convert(ctx: click.Context, paper_ids: list[str], mode: str, pdf_dir: str, batch: bool):
    """Convert papers to Markdown with dual-mode support.

    Modes:
    - auto: Try LaTeX for arXiv papers, fallback to PyMuPDF
    - latex: Force LaTeX download (arXiv only)
    - pymupdf: Force PyMuPDF text extraction

    Examples:
        # Auto-convert specific papers
        paperpulse convert 2604.08545v1 2604.08544v1

        # Force LaTeX for arXiv papers
        paperpulse convert 2604.08545v1 --mode latex

        # Batch convert all pending papers
        paperpulse convert --batch

        # Use PyMuPDF for non-arXiv
        paperpulse convert paper-abc123 --mode pymupdf --pdf-dir data/pdfs
    """
    from .converter.converter import PDFConverter

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Determine preference
    prefer_latex = mode in ("auto", "latex")
    force_mode = mode if mode != "auto" else None

    # Initialize converter
    converter = PDFConverter(
        output_dir=config.storage.markdown_dir,
        latex_dir=config.storage.latex_dir,
        prefer_latex=prefer_latex,
        timeout=60
    )

    # Get papers to convert
    if batch or not paper_ids:
        # Convert all papers without markdown
        papers = db.get_papers(limit=50)
        to_convert = [p for p in papers if not p.markdown_path]
    else:
        to_convert = []
        for pid in paper_ids:
            paper = db.get_paper(pid)
            if paper:
                to_convert.append(paper)
            elif converter.SUPPORTED_ARXIV_PATTERN.match(pid):
                # Create minimal paper for arXiv ID
                from .storage.models import Paper
                paper = Paper(paper_id=f"arxiv-{pid}", title=f"arXiv:{pid}", arxiv_id=pid)
                to_convert.append(paper)

    if not to_convert:
        click.echo("No papers to convert")
        return

    click.echo(f"📄 Converting {len(to_convert)} papers (mode: {mode})...\n")

    success_count = 0
    latex_count = 0
    pymupdf_count = 0

    for paper in to_convert:
        paper_id = paper.arxiv_id or paper.paper_id
        click.echo(f"   {paper_id}...", nl=False)

        # Get PDF path if available
        pdf_path = paper.pdf_path
        if not pdf_path and pdf_dir:
            # Search for PDF
            from pathlib import Path
            pdf_base = Path(pdf_dir)
            if pdf_base.exists():
                for year_dir in pdf_base.iterdir():
                    if year_dir.is_dir():
                        for month_dir in year_dir.iterdir():
                            if month_dir.is_dir():
                                candidate = month_dir / f"{paper_id}.pdf"
                                if candidate.exists():
                                    pdf_path = str(candidate)
                                    break

        # Convert
        if force_mode == "latex" and not converter.SUPPORTED_ARXIV_PATTERN.match(paper_id):
            click.echo(" ❌ (not arXiv, can't use LaTeX)")
            continue

        result = converter.convert(paper_id, pdf_path)

        if result.success:
            success_count += 1
            if result.mode == "latex":
                latex_count += 1
                click.echo(f" ✅ LaTeX ({result.formulas} formulas)")
            else:
                pymupdf_count += 1
                click.echo(f" ✅ PyMuPDF ({result.pages} pages)")

            # Update paper in DB
            paper.markdown_path = result.markdown_path
            if result.latex_path:
                paper.latex_path = result.latex_path
            db.update_paper(paper)
        else:
            click.echo(f" ❌ {result.error}")

    click.echo(f"\n✅ Converted {success_count}/{len(to_convert)} papers")
    click.echo(f"   LaTeX: {latex_count}, PyMuPDF: {pymupdf_count}")


@main.command()
@click.argument("paper_ids", nargs=-1)
@click.option("--limit", "-l", default=20, help="Maximum papers to analyze")
@click.option("--force", "-f", is_flag=True, help="Force re-analyze even if already analyzed")
@click.pass_context
def analyze(ctx: click.Context, paper_ids: list[str], limit: int, force: bool):
    """Analyze papers using LLM.

    Extracts keywords, innovations, limitations from papers.

    Examples:
        # Analyze specific papers
        paperpulse analyze 2604.08545v1 2604.08544v1

        # Analyze all pending papers
        paperpulse analyze --limit 30

        # Force re-analyze
        paperpulse analyze --force
    """
    from .analysis.backend import create_backend
    from .analysis.paper_analyzer import PaperAnalyzer

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Check backend configuration
    if config.llm.is_acp_backend():
        click.echo(f"🤖 Using ACP backend: {config.llm.backend}")
    else:
        # Check API key for OpenAI backend
        api_key = config.llm.get_api_key()
        if not api_key:
            click.echo("❌ No API key configured")
            click.echo(f"   Set {config.llm.api_key_env} environment variable")
            click.echo("   Or use an ACP backend like pi (config: llm.backend: pi)")
            return

    # Get papers
    if not paper_ids:
        papers = db.get_papers(limit=limit)
        if force:
            # Force re-analyze all papers with content
            papers = [p for p in papers if p.markdown_path or p.abstract]
        else:
            # Only analyze papers without keywords
            papers = [p for p in papers if (p.markdown_path or p.abstract) and not p.keywords]
    else:
        papers = []
        for pid in paper_ids:
            paper = db.get_paper(pid)
            if paper:
                papers.append(paper)

    if not papers:
        if force:
            click.echo("No papers with content to analyze")
        else:
            click.echo("No papers to analyze (use --force to re-analyze)")
        return

    click.echo(f"🤖 Analyzing {len(papers)} papers...")

    # Create backend (OpenAI or ACP)
    backend = create_backend(config.llm)
    analyzer = PaperAnalyzer(backend, db)

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


@main.command("research-idea")
@click.argument("idea_id")
@click.option("--papers", "-p", default=10, help="Number of related papers to include")
@click.option("--mode", "-m", default="full-auto", help="Research mode (full-auto, interactive)")
@click.option("--output", "-o", default="papers", help="Output directory for research artifacts")
@click.pass_context
def research_idea_cmd(ctx: click.Context, idea_id: str, papers: int, mode: str, output: str):
    """Run autonomous research pipeline for an idea using pi.

    This command directly uses pi (via ACP) to run a 10-stage research
    pipeline from idea to paper draft - no external CLI needed.

    Stages:
    1. Idea Refinement
    2. Literature Review
    3. Method Design
    4. Experiment Design
    5. Algorithm Implementation
    6. Synthetic Validation
    7. Expected Results
    8. Paper Writing
    9. Paper Review
    10. Paper Refinement

    Examples:
        paperpulse research-idea idea-20260412-abc123
        paperpulse research-idea idea-xxx --mode interactive
        paperpulse research-idea idea-xxx --papers 15
    """
    from .research.pipeline import ResearchPipeline
    from .storage.models import Idea
    import sqlite3

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Check backend
    if config.llm.is_acp_backend():
        click.echo(f"🤖 Using ACP backend: {config.llm.backend}")
    else:
        api_key = config.llm.get_api_key()
        if not api_key:
            click.echo("❌ No API key configured")
            return

    # Get idea from database
    import json
    conn = sqlite3.connect(config.storage.database)
    cursor = conn.cursor()
    cursor.execute("SELECT idea_id, title, description, score, novelty_score, feasibility_score, impact_score, related_paper_ids FROM ideas WHERE idea_id = ?", (idea_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        click.echo(f"❌ Idea not found: {idea_id}")
        click.echo("   Run 'paperpulse ideas' to see available ideas")
        return

    # Parse related_paper_ids (stored as JSON string in database)
    related_ids = json.loads(row[7]) if row[7] else []

    # Create Idea object
    idea = Idea(
        idea_id=row[0],
        title=row[1],
        description=row[2],
        score=row[3],
        novelty_score=row[4],
        feasibility_score=row[5],
        impact_score=row[6],
        related_paper_ids=related_ids,
    )

    # Get related papers
    related_papers = []
    click.echo(f"   Debug: Looking for papers in {idea.related_paper_ids[:papers]}")
    for paper_id in idea.related_paper_ids[:papers]:
        # paper_id format: "arxiv-2604.xxx"
        paper = db.get_paper(paper_id)
        if paper:
            related_papers.append(paper)
            click.echo(f"      Found: {paper.title[:40]}...")
        else:
            click.echo(f"      Not found: {paper_id}")

    click.echo(f"\n🚀 Starting Research Pipeline")
    click.echo(f"   Idea: {idea.title}")
    click.echo(f"   Score: {idea.score:.2f}")
    click.echo(f"   Related papers: {len(related_papers)}")
    click.echo(f"   Mode: {mode}")
    click.echo(f"   Output: {output}/")

    # Run pipeline
    pipeline = ResearchPipeline(config, db, output_dir=output)
    results = pipeline.run_research(idea, related_papers, mode=mode)

    if results.get("success"):
        click.echo(f"\n✅ Research completed!")
        click.echo(f"   Paper draft: {results.get('paper_path')}")
    else:
        click.echo(f"\n⚠️ Research partially completed")
        for stage_name, stage_result in results.get("stages", {}).items():
            icon = "✅" if stage_result.get("success") else "❌"
            click.echo(f"   {icon} {stage_name}")

@main.command()
@click.option("--num", "-n", default=5, help="Number of ideas to generate")
@click.pass_context
def ideas(ctx: click.Context, num: int):
    """Generate research ideas."""
    from .analysis.backend import create_backend
    from .ideas.generator import IdeaGenerator

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Check backend configuration
    if config.llm.is_acp_backend():
        click.echo(f"💡 Using ACP backend: {config.llm.backend}")
    else:
        # Check API key for OpenAI backend
        api_key = config.llm.get_api_key()
        if not api_key:
            click.echo("❌ No API key configured")
            click.echo("   Set OPENAI_API_KEY or use an ACP backend")
            return

    # Get analyzed papers
    papers = db.get_papers(limit=30)
    analyzed = [p for p in papers if p.keywords or p.innovations]

    if len(analyzed) < 3:
        click.echo("⚠️ Need at least 3 analyzed papers to generate ideas")
        click.echo("   Run: paperpulse analyze")
        return

    click.echo(f"💡 Generating ideas from {len(analyzed)} papers...")

    # Create backend (OpenAI or ACP)
    backend = create_backend(config.llm)
    generator = IdeaGenerator(backend, db, config)

    generated = generator.generate_ideas(analyzed, num_ideas=num)

    if generated:
        click.echo(f"\n✅ Generated {len(generated)} ideas:\n")
        for i, idea in enumerate(generated, 1):
            click.echo(f"  #{i} [{idea.score:.2f}] {idea.title}")
    else:
        click.echo("\n⚠️ No ideas generated")


@main.command("research")
@click.argument("idea_id", required=False)
@click.option("--best", "-b", is_flag=True, help="Auto-research the best scoring idea")
@click.option("--all", "-a", "research_all", is_flag=True, help="Research all high-scoring ideas")
@click.option("--min-score", "-s", default=0.6, help="Minimum idea score threshold")
@click.option("--mode", "-m", default="full-auto", help="Research mode (full-auto, co-pilot, gate-only)")
@click.option("--dry-run", is_flag=True, help="Show config without running")
@click.option("--status", is_flag=True, help="Check research status for idea")
@click.option("--list", "-l", "list_runs", is_flag=True, help="List recent research runs")
@click.pass_context
def research_cmd(ctx: click.Context, idea_id: Optional[str], best: bool, research_all: bool, min_score: float, mode: str, dry_run: bool, status: bool, list_runs: bool):
    """Start AutoResearchClaw research for an idea.

    Usage:
        # Research specific idea
        paperpulse research idea-20260412-abc123

        # Auto-research best idea
        paperpulse research --best

        # Research all good ideas (score >= 0.6)
        paperpulse research --all

        # Check research status
        paperpulse research idea-xxx --status

        # List recent runs
        paperpulse research --list
    """
    from .integration.researchclaw import ResearchClawIntegration

    config = ctx.obj["config"]
    db = ctx.obj["db"]
    integration = ResearchClawIntegration(config, db)

    # List runs mode
    if list_runs:
        runs = integration.list_runs(limit=10)
        if not runs:
            click.echo("No research runs found")
            return
        click.echo("📋 Recent Research Runs:\n")
        for run in runs:
            status_icon = "✅" if run.get("completed") else "⏳"
            click.echo(f"  {status_icon} {run['run_id']}")
            if run.get("has_pdf"):
                click.echo(f"      Paper: {run['path']}/deliverables/paper.pdf")
        return

    # Check availability
    if not integration.is_available():
        click.echo("❌ AutoResearchClaw not available")
        click.echo("   Install: pip install -e /path/to/AutoResearchClaw")
        click.echo(f"   Current path: {config.integration.researchclaw.path}")
        return

    # Research all mode
    if research_all:
        click.echo(f"🚀 Researching all ideas with score >= {min_score}...\n")
        results = integration.research_all_ideas(min_score=min_score)
        click.echo(f"\n📊 Results:\n")
        for idea_id, success, msg in results:
            icon = "✅" if success else "❌"
            click.echo(f"  {icon} {idea_id}: {msg[:50]}..." if len(msg) > 50 else f"  {icon} {idea_id}: {msg}")
        return

    # Best idea mode
    if best:
        click.echo(f"💡 Finding best idea (score >= {min_score})...\n")
        success, msg = integration.research_best_idea(min_score=min_score)
        if success:
            click.echo(f"\n✅ Research started: {msg}")
        else:
            click.echo(f"\n❌ {msg}")
        return

    # Status check mode
    if status and idea_id:
        idea = db.get_idea(idea_id)
        if not idea:
            click.echo(f"❌ Idea not found: {idea_id}")
            return
        if not idea.researchclaw_run_id:
            click.echo("⚠️ Idea not yet researched")
            return
        run_status = integration.get_research_status(idea.researchclaw_run_id)
        if run_status:
            click.echo(f"\n📋 Research Status: {idea.researchclaw_run_id}\n")
            click.echo(f"  Completed: {run_status.get('completed', False)}")
            click.echo(f"  Has paper: {run_status.get('has_paper', False)}")
            click.echo(f"  Has PDF: {run_status.get('has_pdf', False)}")
            if run_status.get('has_pdf'):
                outputs = integration.get_research_output(idea.researchclaw_run_id)
                if outputs:
                    click.echo(f"\n📄 Outputs:")
                    for name, path in outputs.items():
                        if path:
                            click.echo(f"  - {name}: {path}")
        else:
            click.echo("⚠️ Research run not found")
        return

    # Default: research specific idea
    if not idea_id:
        click.echo("❌ Please specify an idea ID or use --best/--all")
        click.echo("   Examples:")
        click.echo("     paperpulse research idea-20260412-abc123")
        click.echo("     paperpulse research --best")
        click.echo("     paperpulse research --all --min-score 0.7")
        return

    idea = db.get_idea(idea_id)
    if not idea:
        click.echo(f"❌ Idea not found: {idea_id}")
        click.echo("   Run 'paperpulse ideas' to see available ideas")
        return

    # Dry run
    if dry_run:
        click.echo(f"\n📋 Research Preview:\n")
        click.echo(f"  Idea: {idea.title}")
        click.echo(f"  Score: {idea.score:.2f}")
        click.echo(f"  Novelty: {idea.novelty_score:.2f}")
        click.echo(f"  Feasibility: {idea.feasibility_score:.2f}")
        click.echo(f"  Impact: {idea.impact_score:.2f}")
        click.echo(f"  Related papers: {len(idea.related_paper_ids)}")
        click.echo(f"  Mode: {mode}")
        click.echo(f"\n  Description:")
        click.echo(f"    {idea.description[:200]}..." if len(idea.description) > 200 else f"    {idea.description}")
        return

    # Start research
    success, result = integration.start_research(idea, mode=mode)

    if success:
        click.echo(f"\n✅ Research completed: {result}")
    else:
        click.echo(f"\n❌ Failed: {result}")


@main.command()
@click.option("--daily", is_flag=True, help="Generate daily report")
@click.option("--weekly", is_flag=True, help="Generate weekly report")
@click.option("--preview", "-p", is_flag=True, help="Preview mode: show abstracts for quick screening")
@click.option("--quality", "-q", is_flag=True, help="Show quality assessment for papers")
@click.option("--limit", "-l", default=10, help="Number of papers to show")
@click.pass_context
def report(ctx: click.Context, daily: bool, weekly: bool, preview: bool, quality: bool, limit: int):
    """Generate reports.

    Preview mode (--preview) shows paper abstracts for quick screening.
    Quality mode (--quality) shows quality assessment.
    """
    from .output.markdown import MarkdownReport

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Preview mode: show abstracts for quick screening
    if preview:
        papers = db.get_recent_papers(days=1, limit=limit)
        if not papers:
            papers = db.get_papers(limit=limit)
        
        click.echo(f"\n{'='*60}")
        click.echo(f"  📚 Paper Preview - Quick Screening")
        click.echo(f"{'='*60}\n")
        
        for i, paper in enumerate(papers, 1):
            title = paper.title[:60] + "..." if len(paper.title) > 60 else paper.title
            click.echo(f"\n{i}. {title}")
            click.echo(f"   📅 {paper.arxiv_id or paper.paper_id}")
            
            # Show abstract (truncated)
            abstract = paper.abstract[:200] + "..." if paper.abstract and len(paper.abstract) > 200 else paper.abstract or "No abstract"
            click.echo(f"   📝 Abstract: {abstract}")
            
            # Show keywords if analyzed
            if paper.keywords:
                click.echo(f"   🏷️ Keywords: {', '.join(paper.keywords[:5])}")
            
            # Quality assessment
            if quality:
                q_score = assess_quality(paper)
                click.echo(f"   ⭐ Quality: {q_score:.1f}/10")
            
            click.echo(f"   {'─'*50}")
        
        click.echo(f"\n💡 Tips:")
        click.echo(f"   - Read full abstract: paperpulse download <id> && paperpulse convert <id>")
        click.echo(f"   - Deep analyze: paperpulse analyze <id>")
        return

    reporter = MarkdownReport(db, config.output.reports_dir)

    if daily or not weekly:
        path = reporter.generate_daily_report()
        click.echo(f"✅ Daily report: {path}")

    if weekly:
        path = reporter.generate_weekly_report()
        click.echo(f"✅ Weekly report: {path}")


def assess_quality(paper: "Paper") -> float:
    """Assess paper quality based on metadata.
    
    Returns score from 0-10.
    """
    score = 5.0  # Base score
    
    # Adjustments
    if paper.keywords:
        score += 1.0  # Has analysis
    
    if paper.innovations and len(paper.innovations) >= 2:
        score += 1.5  # Multiple innovations
    
    if paper.citation_count and paper.citation_count > 50:
        score += 1.5  # Highly cited
    elif paper.citation_count and paper.citation_count > 10:
        score += 0.5  # Moderately cited
    
    if paper.year and paper.year >= 2024:
        score += 0.5  # Recent
    
    if paper.limitations and len(paper.limitations) >= 2:
        score += 0.5  # Has limitations identified
    
    return min(10.0, max(0.0, score))


@main.command("synthesis")
@click.argument("paper_id", required=False)
@click.option("--recent", "-r", is_flag=True, help="Generate for recent papers")
@click.option("--days", "-d", default=1, help="Days to look back for recent papers")
@click.option("--limit", "-l", default=5, help="Maximum papers to process")
@click.pass_context
def synthesis_cmd(ctx: click.Context, paper_id: Optional[str], recent: bool, days: int, limit: int):
    """Generate synthesis report for a paper.

    Reads full paper Markdown (including related work section) and
    generates comprehensive research synthesis report using LLM.

    Examples:
        # Generate synthesis for specific paper
        paperpulse synthesis 2604.08523v1

        # Generate for recent papers
        paperpulse synthesis --recent --days 1 --limit 5
    """
    from .analysis.backend import create_backend
    from .output.synthesis import SynthesisReport

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Check backend
    if config.llm.is_acp_backend():
        click.echo(f"🤖 Using ACP backend: {config.llm.backend}")
    else:
        api_key = config.llm.get_api_key()
        if not api_key:
            click.echo("❌ No API key configured")
            return

    # Create backend
    backend = create_backend(config.llm)
    synthesizer = SynthesisReport(db, config, backend)

    if recent:
        # Generate for recent papers
        click.echo(f"📚 Generating synthesis reports for recent papers (last {days} days)...")
        paths = synthesizer.generate_for_recent(days=days, limit=limit)
        
        if paths:
            click.echo(f"\n✅ Generated {len(paths)} synthesis reports:")
            for path in paths:
                click.echo(f"   - {path}")
        else:
            click.echo("\n⚠️ No papers with markdown content found")
    elif paper_id:
        # Generate for specific paper
        # Try multiple lookup methods
        paper = db.get_paper(paper_id)
        if not paper:
            paper = db.get_paper(f"arxiv-{paper_id}")
        if not paper:
            paper = db.get_paper_by_arxiv_id(paper_id)
        
        if not paper:
            click.echo(f"❌ Paper not found: {paper_id}")
            click.echo("   Available papers with markdown:")
            papers = db.get_papers(limit=10)
            for p in papers:
                if p.markdown_path:
                    click.echo(f"   - {p.arxiv_id or p.paper_id}: {p.title[:40]}...")
            return
        
        if not paper.markdown_path:
            click.echo(f"❌ Paper has no markdown content. Run: paperpulse convert {paper_id}")
            return
        
        click.echo(f"📝 Generating synthesis report for: {paper.title[:50]}...")
        path = synthesizer.generate_report(paper)
        click.echo(f"\n✅ Synthesis report: {path}")
    else:
        click.echo("Please specify a paper_id or use --recent")
        click.echo("Examples:")
        click.echo("  paperpulse synthesis 2604.08523v1")
        click.echo("  paperpulse synthesis --recent")


@main.command("auto-daily")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.pass_context
def auto_daily(ctx: click.Context, dry_run: bool):
    """Daily automated paper reading with domain weighting.

    Collects papers based on configured domain weights:
    - Math: 10%
    - AI Theory: 30%
    - AI OS/Compiler: 30%
    - AI Infrastructure: 30%

    Then automatically:
    1. Downloads papers
    2. Converts to Markdown
    3. Generates synthesis reports

    Usage:
        paperpulse auto-daily           # Run daily pipeline
        paperpulse auto-daily --dry-run # Preview only
    """
    import random
    import time
    from .collectors.arxiv import ArxivCollector
    from .analysis.backend import create_backend
    from .output.synthesis import SynthesisReport
    
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    
    # Get daily reading config
    dr_config = config.daily_reading
    if not dr_config.enabled:
        click.echo("❌ Daily reading is disabled in config")
        return
    
    # Calculate papers per domain based on weights
    total = dr_config.total_papers
    domains = dr_config.domains
    total_weight = sum(d.weight for d in domains)
    
    domain_papers = {}
    for domain in domains:
        count = int(total * domain.weight / total_weight)
        domain_papers[domain.name] = {
            "count": count,
            "categories": domain.categories,
            "keywords": domain.keywords,
        }
    
    # Adjust to ensure total papers
    actual_total = sum(d["count"] for d in domain_papers.values())
    if actual_total < total:
        # Add to largest domain
        largest = max(domain_papers.keys(), key=lambda k: domain_papers[k]["count"])
        domain_papers[largest]["count"] += total - actual_total
    
    if dry_run:
        click.echo("\n📋 Daily Reading Preview:\n")
        click.echo(f"Total papers: {total}\n")
        for name, info in domain_papers.items():
            click.echo(f"  {name}: {info['count']} papers")
            if info['categories']:
                click.echo(f"    Categories: {', '.join(info['categories'])}")
            if info['keywords']:
                click.echo(f"    Keywords: {', '.join(info['keywords'])}")
        click.echo("\n💡 Run without --dry-run to execute")
        return
    
    # Execute collection
    click.echo("\n" + "="*60)
    click.echo("  📚 Daily Automated Paper Reading")
    click.echo("="*60 + "\n")
    
    all_papers = []
    
    for domain_name, info in domain_papers.items():
        click.echo(f"📥 Collecting {info['count']} papers from {domain_name}...")
        
        # Collect from categories
        if info['categories']:
            collector = ArxivCollector(
                categories=info['categories'],
                keywords=info['keywords'],
                max_papers=info['count'] * 2,  # Get more to allow filtering
            )
            
            # Try with retries
            max_retries = 3
            papers = []
            for retry in range(max_retries):
                try:
                    papers = collector.get_recent(days=7)
                    break
                except Exception as e:
                    if retry < max_retries - 1:
                        click.echo(f"   Retry {retry+1}/{max_retries}...")
                        time.sleep(10)  # Wait longer before retry
                    else:
                        click.echo(f"   ❌ Failed: {e}")
            
            # Random selection
            if len(papers) > info['count']:
                papers = random.sample(papers, info['count'])
            
            all_papers.extend(papers)
            click.echo(f"   Found {len(papers)} papers")
            
            # Wait between domains to avoid rate limiting
            time.sleep(5)
        else:
            click.echo(f"   ⚠️ No categories configured for {domain_name}")
    
    # Save to database
    if all_papers:
        db.insert_papers(all_papers)
        click.echo(f"\n✅ Saved {len(all_papers)} papers to database")
    else:
        click.echo("\n⚠️ No papers found")
        return
    
    # Download papers
    click.echo("\n📥 Downloading papers...")
    from .downloader.pdf import DocumentDownloader
    downloader = DocumentDownloader(config, db)
    
    for paper in all_papers:
        if paper.arxiv_id:
            click.echo(f"   {paper.arxiv_id}...", nl=False)
            try:
                success, pdf_path, latex_path = downloader.download_paper(paper)
                if success:
                    paper.pdf_path = pdf_path
                    paper.latex_path = latex_path
                    db.update_paper(paper)
                    click.echo(" ✅")
                else:
                    click.echo(" ❌")
            except Exception as e:
                click.echo(f" ❌ ({e})")
            time.sleep(1)  # Rate limiting
    
    # Convert papers
    click.echo("\n📄 Converting papers to Markdown...")
    from .converter.converter import PDFConverter
    converter = PDFConverter(
        output_dir=config.storage.markdown_dir,
        latex_dir=config.storage.latex_dir,
        prefer_latex=config.document.prefer_latex_source,
    )
    
    converted_papers = []
    for paper in all_papers:
        if paper.pdf_path:
            click.echo(f"   {paper.arxiv_id or paper.paper_id}...", nl=False)
            try:
                result = converter.convert(paper.arxiv_id or paper.paper_id, paper.pdf_path)
                if result.success:
                    paper.markdown_path = result.markdown_path
                    db.update_paper(paper)
                    converted_papers.append(paper)
                    click.echo(f" ✅ ({result.formulas if result.mode == 'latex' else result.pages} {result.mode})")
                else:
                    click.echo(" ❌")
            except Exception as e:
                click.echo(f" ❌ ({e})")
    
    # Generate synthesis reports
    click.echo("\n📝 Generating synthesis reports...")
    
    backend = create_backend(config.llm)
    synthesizer = SynthesisReport(db, config, backend)
    
    report_paths = []
    for paper in converted_papers:
        click.echo(f"   {paper.arxiv_id or paper.paper_id}...", nl=False)
        try:
            path = synthesizer.generate_report(paper)
            report_paths.append(path)
            click.echo(" ✅")
        except Exception as e:
            click.echo(f" ❌ ({e})")
        # Wait longer to avoid ACP concurrency issues
        time.sleep(10)  # 10 seconds between each LLM call
    
    # Summary
    click.echo("\n" + "="*60)
    click.echo("  ✅ Daily Reading Complete")
    click.echo("="*60 + "\n")
    click.echo(f"Papers collected: {len(all_papers)}")
    click.echo(f"Papers converted: {len(converted_papers)}")
    click.echo(f"Synthesis reports: {len(report_paths)}")
    
    if report_paths:
        click.echo("\n📊 Reports:")
        for path in report_paths:
            click.echo(f"   - {path}")


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

    # LLM Backend
    if config.llm.is_acp_backend():
        # ACP backend check
        click.echo(f"○ LLM backend: {config.llm.backend} (ACP)")
        
        # Try to check if agent is available
        try:
            from .analysis.backend import create_backend
            backend = create_backend(config.llm)
            success, msg = backend.preflight()
            if success:
                click.echo(f"✓ Agent available: {msg}")
            else:
                click.echo(f"✗ Agent check: {msg}")
        except Exception as e:
            click.echo(f"✗ Agent check failed: {e}")
    else:
        # OpenAI backend check
        api_key = config.llm.get_api_key()
        if api_key:
            click.echo(f"✓ LLM backend: openai (API key set)")
            click.echo(f"  Model: {config.llm.primary_model}")
        else:
            click.echo(f"✗ LLM backend: openai (API key not set)")
            click.echo(f"  Set {config.llm.api_key_env} environment variable")
            click.echo("  Or use an ACP backend in config.yaml:")
            click.echo("    llm:")
            click.echo("      backend: pi  # or claude-code, copilot-cli, etc.")

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


@main.command("auto")
@click.option("--collect-days", "-d", default=7, help="Days to look back for papers")
@click.option("--collect-limit", "-c", default=20, help="Maximum papers to collect")
@click.option("--analyze-limit", "-a", default=10, help="Maximum papers to analyze")
@click.option("--num-ideas", "-n", default=3, help="Number of ideas to generate")
@click.option("--min-score", "-s", default=0.65, help="Minimum score for auto-research")
@click.option("--auto-research", is_flag=True, help="Auto-start research for top ideas")
@click.option("--daemon", is_flag=True, help="Run as daemon (daily execution)")
@click.option("--dry-run", is_flag=True, help="Preview mode without execution")
@click.pass_context
def auto_cmd(ctx: click.Context, collect_days: int, collect_limit: int, analyze_limit: int, num_ideas: int, min_score: float, auto_research: bool, daemon: bool, dry_run: bool):
    """Fully automated pipeline: Collect → Analyze → Ideate → Research.

    This command runs the complete automation:

    1. Collects papers from arXiv/Semantic Scholar
    2. Analyzes papers with LLM to extract insights
    3. Generates research ideas from paper analysis
    4. Optionally starts AutoResearchClaw research

    Usage:
        # Run once (full pipeline)
        paperpulse auto

        # Preview mode
        paperpulse auto --dry-run

        # With auto-research
        paperpulse auto --auto-research --min-score 0.7

        # Run as daemon (daily monitoring)
        paperpulse auto --daemon --auto-research
    """
    from .integration.auto_pipeline import AutoPipeline

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    pipeline = AutoPipeline(config, db)

    if daemon:
        # Daemon mode: run periodically
        click.echo("\n🔄 Starting Auto-Pipeline Daemon")
        click.echo("   This will run daily: collect → analyze → ideate → research")
        click.echo("   Press Ctrl+C to stop\n")
        pipeline.run_daemon(interval_hours=24)
    else:
        # Single run
        stats = pipeline.run_full_pipeline(
            collect_days=collect_days,
            collect_limit=collect_limit,
            analyze_limit=analyze_limit,
            num_ideas=num_ideas,
            min_score=min_score,
            auto_research=auto_research,
            dry_run=dry_run,
        )

        # Return appropriate exit code
        if stats.get("errors"):
            ctx.exit(1)


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


@main.group("notion")
@click.pass_context
def notion_cmd(ctx: click.Context):
    """Sync reports to Notion using notionary.
    
    Requires notionary package and Notion Integration token.
    
    Setup:
        1. Create Notion Integration: https://www.notion.so/my-integrations
        2. Copy integration token (secret_xxx)
        3. Set environment variable: export NOTION_API_KEY='secret_xxx'
        4. Share a Notion page/database with your integration
        5. Configure target in config.yaml or use CLI options
    
    Examples:
        paperpulse notion test                     # Test connection
        paperpulse notion list                     # List accessible pages
        paperpulse notion sync report.md           # Sync single file
        paperpulse notion sync ./reports/          # Sync directory
    """
    pass


@notion_cmd.command("test")
@click.pass_context
def notion_test(ctx: click.Context):
    """Test Notion API connection."""
    config = ctx.obj["config"]
    
    api_key = config.notion.get_api_key()
    if not api_key:
        click.echo("❌ No Notion API key configured")
        click.echo("")
        click.echo("Setup:")
        click.echo("  1. Create Notion Integration: https://www.notion.so/my-integrations")
        click.echo("  2. Copy integration token (secret_xxx)")
        click.echo("  3. Set environment variable: export NOTION_API_KEY='secret_xxx'")
        click.echo("  4. Or add to config.yaml:")
        click.echo("     notion:")
        click.echo("       api_key: secret_xxx")
        sys.exit(1)
    
    click.echo("🔍 Testing Notion API connection...")
    
    try:
        from .output.notion import test_connection
        result = test_connection(api_key)
        
        if result.get("success"):
            click.echo("✅ Connection successful")
            click.echo(f"   Bot: {result.get('user', 'Unknown')}")
            click.echo(f"   Bot ID: {result.get('bot_id', 'N/A')}")
        else:
            click.echo(f"❌ Connection failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
    except ImportError as e:
        click.echo(f"❌ {e}")
        click.echo("   Install with: uv pip install notionary")
        sys.exit(1)


@notion_cmd.command("list")
@click.option("--query", "-q", help="Search query")
@click.option("--databases", "-d", is_flag=True, help="List databases (data sources) instead")
@click.pass_context
def notion_list(ctx: click.Context, query: Optional[str], databases: bool):
    """List accessible Notion pages or databases."""
    import asyncio
    
    config = ctx.obj["config"]
    api_key = config.notion.get_api_key()
    
    if not api_key:
        click.echo("❌ No Notion API key configured")
        sys.exit(1)
    
    try:
        from .output.notion import NotionSync
        
        async def _list():
            async with NotionSync(api_key=api_key) as sync:
                if databases:
                    return await sync.list_data_sources(query=query)
                else:
                    return await sync.list_pages(query=query)
        
        items = asyncio.run(_list())
        
        if not items:
            click.echo("No items found")
            if not databases:
                click.echo("")
                click.echo("Tip: Share pages with your integration to make them accessible")
            return
        
        click.echo(f"Found {len(items)} items:")
        click.echo("")
        for item in items:
            click.echo(f"  - {item['title']}")
            click.echo(f"    ID: {item['id']}")
            click.echo(f"    URL: {item['url']}")
            click.echo("")
        
    except ImportError as e:
        click.echo(f"❌ {e}")
        click.echo("   Install with: uv pip install notionary")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}")
        sys.exit(1)


@notion_cmd.command("sync")
@click.argument("path", type=click.Path(exists=True))
@click.option("--target-page", "-p", help="Target page title or ID")
@click.option("--target-database", "-d", help="Target database title or ID")
@click.option("--title", "-t", help="Custom page title (for single file)")
@click.option("--pattern", default="*.md", help="File pattern (for directory)")
@click.option("--recursive", "-r", is_flag=True, help="Search recursively (for directory)")
@click.option("--rate-limit", default=0.5, help="Rate limit delay in seconds")
@click.option("--dry-run", is_flag=True, help="Preview mode without syncing")
@click.option("--force", "-f", is_flag=True, help="Force sync all files (ignore modification check)")
@click.pass_context
def notion_sync_cmd(
    ctx: click.Context,
    path: str,
    target_page: Optional[str],
    target_database: Optional[str],
    title: Optional[str],
    pattern: str,
    recursive: bool,
    rate_limit: float,
    dry_run: bool,
    force: bool,
):
    """Sync Markdown file(s) to Notion.
    
    PATH can be a single file or a directory.
    
    Smart incremental sync:
    - New files: Create new Notion pages
    - Modified files: Update existing Notion pages
    - Unchanged files: Skip (compare file mtime with sync time)
    
    Examples:
        paperpulse notion sync report.md -p "My Notes"
        paperpulse notion sync ./reports/ -d "PaperPulse Database"
        paperpulse notion sync ./reports/ --force  # Sync all files
    """
    import asyncio
    from pathlib import Path
    
    config = ctx.obj["config"]
    api_key = config.notion.get_api_key()
    
    if not api_key:
        click.echo("❌ No Notion API key configured")
        sys.exit(1)
    
    # Use config defaults if not specified
    target_page = target_page or config.notion.target_page
    target_database = target_database or config.notion.target_database
    
    if not target_page and not target_database:
        click.echo("❌ No target specified")
        click.echo("")
        click.echo("Options:")
        click.echo("  --target-page: Sync to a Notion page")
        click.echo("  --target-database: Sync to a Notion database")
        click.echo("  Or configure in config.yaml:")
        click.echo("    notion:")
        click.echo('      target_page: "My Page" or target_database: "My DB"')
        sys.exit(1)
    
    path_obj = Path(path)
    
    if dry_run:
        click.echo("⚠️  Dry-run mode: preview only")
        click.echo("")
    
    try:
        from .output.notion import NotionSync
        
        async def _sync():
            async with NotionSync(
                api_key=api_key,
                target_page=target_page,
                target_database=target_database,
                rate_limit_delay=rate_limit,
            ) as sync:
                if path_obj.is_file():
                    # Single file
                    click.echo(f"📄 Syncing: {path_obj.name}")
                    
                    if dry_run:
                        # Preview: read file and show info
                        with open(path_obj, encoding="utf-8") as f:
                            content = f.read()
                        
                        # Extract title
                        file_title = title
                        if not file_title:
                            for line in content.split("\n"):
                                if line.startswith("#"):
                                    file_title = line.lstrip("#").strip()
                                    break
                            if not file_title:
                                file_title = path_obj.stem
                        
                        click.echo(f"   Title: {file_title}")
                        click.echo(f"   Content length: {len(content)} chars")
                        click.echo(f"   Target: {target_database or target_page}")
                        click.echo("   ✅ Preview complete")
                        return [{"success": True, "dry_run": True}]
                    else:
                        result = await sync.sync_file(str(path_obj), title=title)
                        return [result]
                else:
                    # Directory
                    click.echo(f"📁 Syncing directory: {path_obj}")
                    click.echo(f"   Pattern: {pattern}")
                    click.echo(f"   Recursive: {recursive}")
                    click.echo(f"   Target: {target_database or target_page}")
                    click.echo("")
                    
                    if dry_run:
                        # Preview: list files
                        if recursive:
                            files = list(path_obj.rglob(pattern))
                        else:
                            files = list(path_obj.glob(pattern))
                        
                        click.echo(f"Found {len(files)} files:")
                        for f in files:
                            click.echo(f"  - {f.name}")
                        click.echo("")
                        click.echo("   ✅ Preview complete")
                        return [{"success": True, "dry_run": True}]
                    else:
                        if force:
                            click.echo("   Mode: Force sync all files")
                        else:
                            click.echo("   Mode: Smart incremental sync")
                            click.echo("     - New files: Create new pages")
                            click.echo("     - Modified files: Update existing pages")
                            click.echo("     - Unchanged files: Skip")
                        click.echo("")
                        
                        return await sync.sync_directory(
                            str(path_obj),
                            pattern=pattern,
                            recursive=recursive,
                            skip_existing=not force,  # Default: smart incremental, --force: sync all
                        )
        
        results = asyncio.run(_sync())
        
        # Show results
        if not dry_run:
            success_count = sum(1 for r in results if r.get("success"))
            total_count = len(results)
            
            click.echo("")
            click.echo("=" * 60)
            click.echo("  Sync Summary")
            click.echo("=" * 60)
            click.echo(f"  Total: {total_count}")
            click.echo(f"  Successful: {success_count}")
            click.echo(f"  Failed: {total_count - success_count}")
            
            if success_count > 0:
                click.echo("")
                click.echo("  Notion URLs:")
                for r in results:
                    if r.get("url"):
                        click.echo(f"    - {r['url']}")
        
        # Exit code
        if any(not r.get("success") for r in results):
            sys.exit(1)
        
    except ImportError as e:
        click.echo(f"❌ {e}")
        click.echo("   Install with: uv pip install notionary")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}")
        sys.exit(1)




@notion_cmd.command("cleanup")
@click.option("--dry-run", is_flag=True, help="Preview duplicates without removing")
@click.pass_context
def notion_cleanup_cmd(ctx: click.Context, dry_run: bool):
    """Remove duplicate pages from Notion database.
    
    Finds pages with duplicate titles and removes older duplicates.
    Keeps the most recently created page for each title.
    
    Examples:
        paperpulse notion cleanup           # Remove duplicates
        paperpulse notion cleanup --dry-run # Preview only
    """
    import asyncio
    from collections import defaultdict
    from datetime import datetime
    
    config = ctx.obj["config"]
    api_key = config.notion.get_api_key()
    
    if not api_key:
        click.echo("❌ No Notion API key configured")
        sys.exit(1)
    
    try:
        from .output.notion import _get_notionary
        
        Notionary, _, _ = _get_notionary()
        client = Notionary(api_key=api_key)
        
        click.echo("📋 Getting all pages from Notion...")
        
        async def cleanup():
            all_pages = await client.pages.list(page_size=100)
            click.echo(f"   Found {len(all_pages)} total pages")
            
            # Group by title
            title_groups = defaultdict(list)
            for page in all_pages:
                title = page.title if hasattr(page, 'title') else str(page.id)
                if not title:
                    title = str(page.id)
                title_groups[title].append(page)
            
            # Find duplicates
            duplicates = {k: v for k, v in title_groups.items() if len(v) > 1}
            
            if not duplicates:
                click.echo("✅ No duplicates found!")
                return
            
            total_to_remove = sum(len(v)-1 for v in duplicates.values())
            click.echo("")
            click.echo(f"🔍 Found {len(duplicates)} titles with duplicates")
            click.echo(f"⚠️  Total pages to remove: {total_to_remove}")
            click.echo("")
            
            if dry_run:
                click.echo("Dry-run mode - showing duplicates only:")
                for title, pages in sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
                    display_title = title[:50] if len(title) > 50 else title
                    click.echo(f"  '{display_title}': {len(pages)} copies")
                click.echo("")
                click.echo("   Run without --dry-run to remove duplicates")
                return
            
            click.echo("Removing duplicates (keeping latest for each title)...")
            click.echo("")
            
            removed_count = 0
            kept_count = 0
            
            for title, pages in sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True):
                sorted_pages = sorted(pages, key=lambda p: p.created_time if hasattr(p, 'created_time') else datetime.min, reverse=True)
                keep_page = sorted_pages[0]
                remove_pages = sorted_pages[1:]
                
                display_title = title[:40] if len(title) > 40 else title
                click.echo(f"'{display_title}':")
                kept_count += 1
                
                for page in remove_pages:
                    try:
                        await page.trash()
                        removed_count += 1
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        click.echo(f"   ❌ Failed: {e}")
            
            click.echo("")
            click.echo("=" * 50)
            click.echo("Cleanup Summary")
            click.echo("=" * 50)
            click.echo(f"  Pages kept: {kept_count}")
            click.echo(f"  Pages removed: {removed_count}")
            click.echo(f"  Pages remaining: {len(all_pages) - removed_count}")
        
        asyncio.run(cleanup())
        
    except ImportError as e:
        click.echo(f"❌ {e}")
        click.echo("   Install with: uv pip install notionary")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}")
        sys.exit(1)



@main.command("auto-research")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--skip-collection", is_flag=True, help="Skip paper collection (use existing)")
@click.option("--skip-ideas", is_flag=True, help="Skip idea generation")
@click.option("--skip-experiment", is_flag=True, help="Skip AutoResearchClaw experiment")
@click.option("--min-score", "-s", default=0.7, help="Minimum idea score for experiment")
@click.option("--max-experiments", default=1, help="Maximum experiments to run")
@click.pass_context
def auto_research_cmd(
    ctx: click.Context,
    dry_run: bool,
    skip_collection: bool,
    skip_ideas: bool,
    skip_experiment: bool,
    min_score: float,
    max_experiments: int,
):
    """Complete daily research automation pipeline.

    Full pipeline:
    1. Collect papers (domain-weighted)
    2. Download & convert to Markdown
    3. Generate synthesis reports
    4. Sync to Notion
    5. Generate research ideas
    6. Check feasibility (GPU, environment)
    7. Run AutoResearchClaw experiment

    Usage:
        paperpulse auto-research                 # Full pipeline
        paperpulse auto-research --dry-run       # Preview only
        paperpulse auto-research --skip-collection  # Use existing papers
        paperpulse auto-research --skip-experiment   # Stop before experiment
    """
    import subprocess
    import time

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    click.echo("\n" + "="*60)
    click.echo("  🔬 PaperPulse + AutoResearchClaw Daily Research")
    click.echo("="*60 + "\n")

    if dry_run:
        click.echo("📋 DRY RUN - Preview mode\n")
        click.echo("Pipeline steps:")
        click.echo("  1. Collect papers (10 papers, domain-weighted)")
        click.echo("  2. Download & convert to Markdown")
        click.echo("  3. Generate synthesis reports")
        click.echo("  4. Sync to Notion")
        click.echo("  5. Generate research ideas (5 ideas)")
        click.echo("  6. Check feasibility")
        click.echo("  7. Run AutoResearchClaw (top idea)")
        click.echo("\n💡 Run without --dry-run to execute")
        return

    # ========================================
    # Phase 1: Paper Collection & Analysis
    # ========================================
    if not skip_collection:
        click.echo("\n[Phase 1] Paper Collection & Analysis\n")
        
        # Invoke auto-daily command
        ctx.invoke(auto_daily)
    else:
        click.echo("\n[Phase 1] Skipping collection (using existing papers)\n")

    # ========================================
    # Phase 2: Sync to Notion
    # ========================================
    click.echo("\n[Phase 2] Sync to Notion\n")
    
    reports_dir = config.storage.reports_dir
    if reports_dir.exists():
        # Invoke notion sync
        notion_ctx = click.Context(notion_sync_cmd, parent=ctx)
        notion_ctx.invoke(notion_sync_cmd, path=str(reports_dir / "synthesis"))

    # ========================================
    # Phase 3: Generate Ideas
    # ========================================
    if not skip_ideas:
        click.echo("\n[Phase 3] Generate Research Ideas\n")
        
        # Invoke ideas command
        ctx.invoke(ideas, num=5)
    else:
        click.echo("\n[Phase 3] Skipping idea generation\n")

    # ========================================
    # Phase 4: Feasibility Check
    # ========================================
    click.echo("\n[Phase 4] Feasibility Check\n")

    # Check GPU
    gpu_available = False
    gpu_info = "Not available"
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            gpu_available = True
            gpu_info = result.stdout.strip()
            click.echo(f"  ✅ GPU: {gpu_info}")
        else:
            click.echo("  ⚠️  GPU: Not available")
    except Exception:
        click.echo("  ⚠️  GPU: Not available")

    # Check AutoResearchClaw
    researchclaw_path = Path(config.integration.researchclaw.path)
    if researchclaw_path.exists():
        click.echo(f"  ✅ AutoResearchClaw: {researchclaw_path}")
    else:
        click.echo("  ⚠️  AutoResearchClaw: Not found")
        skip_experiment = True

    # Check Python/uv
    click.echo(f"  ✅ Python: {subprocess.run(['python3', '--version'], capture_output=True, text=True).stdout.strip()}")

    # ========================================
    # Phase 5: Run AutoResearchClaw
    # ========================================
    if not skip_experiment:
        click.echo("\n[Phase 5] AutoResearchClaw Experiment\n")

        # Get top ideas
        top_ideas = db.get_top_ideas(limit=10)
        feasible_ideas = [i for i in top_ideas if i.score >= min_score and not i.is_researched]

        if not feasible_ideas:
            click.echo("  ⚠️  No feasible ideas found (score >= {})".format(min_score))
            click.echo("  💡 Run with lower --min-score or generate more ideas")
        else:
            click.echo(f"  💡 Found {len(feasible_ideas)} feasible ideas")
            
            # Run experiments
            for i, idea in enumerate(feasible_ideas[:max_experiments]):
                click.echo(f"\n  Experiment {i+1}/{max_experiments}:")
                click.echo(f"    Idea: {idea.title[:50]}...")
                click.echo(f"    Score: {idea.score:.2f}")
                
                # Invoke research command
                success, msg = ctx.invoke(research_cmd, idea_id=idea.idea_id)
                
                if success:
                    click.echo(f"    ✅ Experiment completed: {msg}")
                else:
                    click.echo(f"    ❌ Experiment failed: {msg}")

    # ========================================
    # Summary
    # ========================================
    click.echo("\n" + "="*60)
    click.echo("  ✅ Daily Research Complete")
    click.echo("="*60 + "\n")

    # Get stats
    papers = db.get_papers(limit=100)
    analyzed = [p for p in papers if p.keywords or p.innovations]
    ideas_list = db.get_top_ideas(limit=20)
    researched = [i for i in ideas_list if i.is_researched]

    click.echo(f"Papers collected: {len(papers)}")
    click.echo(f"Papers analyzed: {len(analyzed)}")
    click.echo(f"Ideas generated: {len(ideas_list)}")
    click.echo(f"Experiments run: {len(researched)}")



if __name__ == "__main__":
    main()