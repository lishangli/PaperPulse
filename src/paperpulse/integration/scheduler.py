"""Scheduler for automated paper monitoring."""

from __future__ import annotations

import signal
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..config import PaperPulseConfig
from ..storage.database import Database


class PaperPulseScheduler:
    """Scheduler for automated paper monitoring tasks."""

    def __init__(self, config: PaperPulseConfig, db: Database):
        """Initialize scheduler.

        Args:
            config: PaperPulse configuration
            db: Database instance
        """
        self.config = config
        self.db = db
        self._running = False
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        """Start the scheduler."""
        if not self.config.scheduler.enabled:
            print("Scheduler is disabled in config")
            return

        self._running = True

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        print(f"Scheduler started")
        print(f"  Daily monitor: {self.config.scheduler.daily_monitor}")
        print(f"  Daily report: {self.config.scheduler.daily_report}")

        # Simple polling loop
        # In production, use a proper scheduler like APScheduler
        try:
            while self._running:
                self._check_and_run()
                threading.Event().wait(60)  # Check every minute
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        print("Scheduler stopped")

    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        print(f"\nReceived signal {signum}, stopping...")
        self.stop()
        sys.exit(0)

    def _check_and_run(self) -> None:
        """Check if any tasks should run."""
        now = datetime.now()

        # Check daily monitor
        if self._should_run(self.config.scheduler.daily_monitor, "daily_monitor"):
            self._run_daily_monitor()

        # Check daily report
        if self._should_run(self.config.scheduler.daily_report, "daily_report"):
            self._run_daily_report()

    def _should_run(self, cron_expr: str, task_name: str) -> bool:
        """Check if a task should run based on cron expression.

        Simplified cron parsing - only handles basic patterns.
        """
        # Parse cron: "minute hour day month weekday"
        parts = cron_expr.split()
        if len(parts) != 5:
            return False

        minute, hour, day, month, weekday = parts
        now = datetime.now()

        # Check if we already ran today
        last_run_file = Path(f".{task_name}_last_run")
        if last_run_file.exists():
            try:
                last_run = datetime.fromisoformat(last_run_file.read_text().strip())
                if last_run.date() == now.date():
                    return False
            except:
                pass

        # Check hour and minute
        try:
            if minute != "*" and int(minute) != now.minute:
                return False
            if hour != "*" and int(hour) != now.hour:
                return False
        except ValueError:
            return False

        return True

    def _mark_run(self, task_name: str) -> None:
        """Mark a task as run."""
        last_run_file = Path(f".{task_name}_last_run")
        last_run_file.write_text(datetime.now().isoformat())

    def _run_daily_monitor(self) -> None:
        """Run daily monitoring task."""
        print(f"[{datetime.now().isoformat()}] Running daily monitor...")

        try:
            # Import here to avoid circular imports
            from ..collectors.arxiv import ArxivCollector
            from ..downloader.pdf import DocumentDownloader

            # Collect papers
            collector = ArxivCollector(
                categories=self.config.sources.arxiv.categories,
                keywords=self.config.sources.arxiv.keywords,
                max_papers=self.config.sources.arxiv.max_papers_per_day,
            )

            papers = collector.get_recent(days=1)

            if papers:
                # Save to database
                self.db.insert_papers(papers)
                print(f"  Collected {len(papers)} papers")

            self._mark_run("daily_monitor")

        except Exception as e:
            print(f"  Error in daily monitor: {e}")

    def _run_daily_report(self) -> None:
        """Run daily report generation."""
        print(f"[{datetime.now().isoformat()}] Generating daily report...")

        try:
            from ..output.markdown import MarkdownReport
            from ..output.obsidian import ObsidianWriter

            # Generate Markdown report
            reporter = MarkdownReport(self.db, self.config.output.reports_dir)
            report_path = reporter.generate_daily_report()
            print(f"  Report saved: {report_path}")

            # Sync to Obsidian
            if self.config.obsidian.enabled:
                obsidian = ObsidianWriter(self.config, self.db)
                papers = self.db.get_recent_papers(days=1)
                ideas = self.db.get_top_ideas(limit=10)

                if papers:
                    obsidian.sync_papers(papers)
                    print(f"  Synced {len(papers)} papers to Obsidian")

                if ideas:
                    obsidian.sync_ideas(ideas)
                    print(f"  Synced {len(ideas)} ideas to Obsidian")

            self._mark_run("daily_report")

        except Exception as e:
            print(f"  Error in daily report: {e}")


def run_once(config: PaperPulseConfig) -> dict:
    """Run monitoring once (for manual execution).

    Args:
        config: PaperPulse configuration

    Returns:
        Results dict
    """
    from ..analysis.llm_client import create_llm_client
    from ..analysis.paper_analyzer import PaperAnalyzer
    from ..analysis.trend_detector import TrendDetector
    from ..collectors.arxiv import ArxivCollector
    from ..downloader.pdf import DocumentDownloader
    from ..ideas.generator import IdeaGenerator
    from ..output.markdown import MarkdownReport
    from ..output.obsidian import ObsidianWriter
    from ..converter.mineru import MinerUConverter

    db = Database(config.storage.database)
    results = {}

    # 1. Collect papers
    print("📊 Collecting papers...")
    collector = ArxivCollector(
        categories=config.sources.arxiv.categories,
        max_papers=config.sources.arxiv.max_papers_per_day,
    )
    papers = collector.get_recent(days=1)
    results["papers_collected"] = len(papers)

    if papers:
        db.insert_papers(papers)
        print(f"  Found {len(papers)} papers")

    # 2. Download documents
    if papers:
        print("📥 Downloading documents...")
        downloader = DocumentDownloader(config, db)
        download_results = downloader.download_papers(papers[:20])  # Limit
        results["papers_downloaded"] = sum(1 for s, _, _ in download_results.values() if s)
        print(f"  Downloaded {results['papers_downloaded']} papers")

    # 3. Convert PDFs to Markdown
    downloaded_papers = [p for p in papers if p.pdf_path]
    if downloaded_papers:
        print("📄 Converting PDFs...")
        converter = MinerUConverter(config.storage.markdown_dir)

        for paper in downloaded_papers[:5]:  # Limit
            if paper.pdf_path:
                success, result = converter.convert(paper.pdf_path)
                if success:
                    paper.markdown_path = result
                    db.update_paper(paper)

        results["papers_converted"] = sum(1 for p in downloaded_papers if p.markdown_path)

    # 4. Analyze papers
    if config.llm.get_api_key():
        print("🤖 Analyzing papers...")
        try:
            llm = create_llm_client(config.llm)
            analyzer = PaperAnalyzer(llm, db)
            analyzed = [p for p in downloaded_papers if p.markdown_path]

            if analyzed:
                analysis_results = analyzer.analyze_papers(analyzed[:10])
                results["papers_analyzed"] = sum(1 for s in analysis_results.values() if s)
                print(f"  Analyzed {results['papers_analyzed']} papers")
        except Exception as e:
            print(f"  Analysis error: {e}")

    # 5. Generate ideas
    if config.ideas.enabled and config.llm.get_api_key():
        print("💡 Generating ideas...")
        try:
            llm = create_llm_client(config.llm)
            generator = IdeaGenerator(llm, db, config)

            analyzed_papers = db.get_papers(status="analyzed", limit=20)
            if analyzed_papers:
                ideas = generator.generate_ideas(analyzed_papers, num_ideas=5)
                results["ideas_generated"] = len(ideas)
                print(f"  Generated {len(ideas)} ideas")
        except Exception as e:
            print(f"  Idea generation error: {e}")

    # 6. Generate report
    print("📝 Generating report...")
    reporter = MarkdownReport(db, config.output.reports_dir)
    report_path = reporter.generate_daily_report()
    results["report_path"] = report_path
    print(f"  Report: {report_path}")

    # 7. Sync to Obsidian
    if config.obsidian.enabled:
        print("📚 Syncing to Obsidian...")
        obsidian = ObsidianWriter(config, db)
        recent_papers = db.get_recent_papers(days=1)
        ideas = db.get_top_ideas(limit=10)

        if recent_papers:
            obsidian.sync_papers(recent_papers)
        if ideas:
            obsidian.sync_ideas(ideas)

        results["obsidian_synced"] = True
        print(f"  Synced to Obsidian")

    return results