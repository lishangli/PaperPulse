"""AutoResearchClaw integration via CLI."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import yaml

from ..config import PaperPulseConfig
from ..storage.database import Database
from ..storage.models import Idea, Paper


class ResearchClawIntegration:
    """Integration with AutoResearchClaw via CLI."""

    def __init__(self, config: PaperPulseConfig, db: Database):
        """Initialize integration.

        Args:
            config: PaperPulse configuration
            db: Database instance
        """
        self.config = config
        self.db = db

        self.researchclaw_path = Path(config.integration.researchclaw.path)
        self.venv_path = Path(config.integration.researchclaw.venv_path)
        self.auto_run = config.integration.researchclaw.auto_run
        self.require_confirmation = config.integration.researchclaw.require_confirmation

    def is_available(self) -> bool:
        """Check if AutoResearchClaw is available."""
        cli_path = self.venv_path / "bin" / "researchclaw"
        return cli_path.exists()

    def start_research(
        self,
        idea: Idea,
        auto_approve: bool = True,
    ) -> tuple[bool, str]:
        """Start AutoResearchClaw research for an idea.

        Args:
            idea: The idea to research
            auto_approve: Auto-approve gate stages

        Returns:
            Tuple of (success, run_id or error message)
        """
        if not self.is_available():
            return False, "AutoResearchClaw not available"

        # Get related papers
        papers = []
        for paper_id in idea.related_paper_ids:
            paper = self.db.get_paper(paper_id)
            if paper:
                papers.append(paper)

        # Generate config
        config_path = self._generate_config(idea, papers)

        # Build command
        cli_path = self.venv_path / "bin" / "researchclaw"
        cmd = [
            str(cli_path),
            "run",
            "--config", str(config_path),
            "--topic", idea.title,
        ]

        if auto_approve:
            cmd.append("--auto-approve")

        # Run
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.researchclaw_path),
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )

            if result.returncode == 0:
                # Extract run ID from output
                run_id = self._extract_run_id(result.stdout)

                # Update idea
                idea.is_researched = True
                idea.researchclaw_run_id = run_id
                self.db.insert_idea(idea)

                return True, run_id
            else:
                return False, f"Research failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return False, "Research timeout"
        except Exception as e:
            return False, f"Error: {e}"

    def _generate_config(self, idea: Idea, papers: list[Paper]) -> Path:
        """Generate AutoResearchClaw config for the idea."""
        config = {
            "project": {
                "name": idea.idea_id,
                "mode": "full-auto",
            },
            "research": {
                "topic": idea.title,
                "domains": [],
            },
            "llm": {
                "provider": "openai-compatible",
                "base_url": self.config.llm.base_url,
                "api_key_env": self.config.llm.api_key_env,
                "primary_model": self.config.llm.primary_model,
                "fallback_models": [self.config.llm.fallback_model],
            },
            "experiment": {
                "mode": "sandbox",
                "sandbox": {
                    "python_path": ".venv/bin/python3",
                },
            },
        }

        # Add keywords as domains
        if papers:
            keywords = set()
            for paper in papers[:5]:
                keywords.update(paper.keywords[:3])
            config["research"]["domains"] = list(keywords)[:5]

        # Write config
        config_path = Path(tempfile.mktemp(suffix=".yaml"))
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        return config_path

    def _extract_run_id(self, output: str) -> str:
        """Extract run ID from researchclaw output."""
        for line in output.split("\n"):
            if "Run ID:" in line or "run_id:" in line.lower():
                # Try to extract ID
                parts = line.split()
                for part in parts:
                    if part.startswith("rc-"):
                        return part
        return ""

    def get_research_status(self, run_id: str) -> Optional[dict]:
        """Get status of a research run.

        Args:
            run_id: Run ID

        Returns:
            Status dict or None
        """
        artifacts_dir = self.researchclaw_path / "artifacts" / run_id

        if not artifacts_dir.exists():
            return None

        # Check for deliverables
        deliverables = artifacts_dir / "deliverables"
        has_paper = (deliverables / "paper.tex").exists()
        has_pdf = (deliverables / "paper.pdf").exists()

        return {
            "run_id": run_id,
            "path": str(artifacts_dir),
            "has_paper": has_paper,
            "has_pdf": has_pdf,
        }

    def get_research_output(self, run_id: str) -> Optional[dict]:
        """Get output files from a research run.

        Args:
            run_id: Run ID

        Returns:
            Dict with paths to output files
        """
        artifacts_dir = self.researchclaw_path / "artifacts" / run_id
        deliverables = artifacts_dir / "deliverables"

        if not deliverables.exists():
            return None

        return {
            "paper_tex": str(deliverables / "paper.tex") if (deliverables / "paper.tex").exists() else None,
            "paper_pdf": str(deliverables / "paper.pdf") if (deliverables / "paper.pdf").exists() else None,
            "references": str(deliverables / "references.bib") if (deliverables / "references.bib").exists() else None,
            "paper_draft": str(artifacts_dir / "paper_draft.md") if (artifacts_dir / "paper_draft.md").exists() else None,
        }