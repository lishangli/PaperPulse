"""Configuration management for PaperPulse."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class ArxivConfig:
    enabled: bool = True
    categories: list[str] = field(default_factory=lambda: ["cs.AI", "cs.CL", "cs.LG"])
    keywords: list[str] = field(default_factory=list)
    max_papers_per_day: int = 100


@dataclass
class SemanticScholarConfig:
    enabled: bool = True
    fields: list[str] = field(default_factory=lambda: ["Artificial Intelligence"])
    max_papers_per_day: int = 50


@dataclass
class PapersWithCodeConfig:
    enabled: bool = True
    areas: list[str] = field(default_factory=lambda: ["natural-language-processing"])
    max_papers_per_day: int = 50


@dataclass
class SourcesConfig:
    arxiv: ArxivConfig = field(default_factory=ArxivConfig)
    semantic_scholar: SemanticScholarConfig = field(default_factory=SemanticScholarConfig)
    papers_with_code: PapersWithCodeConfig = field(default_factory=PapersWithCodeConfig)


@dataclass
class PDFConfig:
    enabled: bool = True
    max_concurrent: int = 5
    retry_count: int = 3
    timeout_sec: int = 60
    max_size_mb: int = 50


@dataclass
class ConverterConfig:
    backend: str = "mineru"
    mineru: dict[str, Any] = field(default_factory=lambda: {"output_format": "markdown"})


@dataclass
class DocumentConfig:
    prefer_latex_source: bool = True
    pdf: PDFConfig = field(default_factory=PDFConfig)
    converter: ConverterConfig = field(default_factory=ConverterConfig)


@dataclass
class LLMConfig:
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""
    primary_model: str = "gpt-4o"
    fallback_model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    
    def get_api_key(self) -> str:
        """Get API key from config or environment."""
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")


@dataclass
class SchedulerConfig:
    enabled: bool = True
    daily_monitor: str = "0 8 * * *"
    daily_report: str = "30 8 * * *"
    weekly_summary: str = "0 9 * * 1"


@dataclass
class ObsidianFoldersConfig:
    papers: str = "Papers"
    ideas: str = "Ideas"
    daily: str = "Daily"
    latex: str = "LaTeX"


@dataclass
class ObsidianConfig:
    enabled: bool = True
    vault_path: str = ""
    folders: ObsidianFoldersConfig = field(default_factory=ObsidianFoldersConfig)


@dataclass
class StorageConfig:
    database: str = "./data/papers.db"
    pdf_dir: str = "./data/pdfs"
    latex_dir: str = "./data/latex"
    markdown_dir: str = "./data/markdown"
    retention_days: int = 90


@dataclass
class OutputConfig:
    reports_dir: str = "./reports"
    formats: list[str] = field(default_factory=lambda: ["markdown", "json"])


@dataclass
class ResearchClawConfig:
    enabled: bool = True
    path: str = "/home/lishangli/repos/AutoResearchClaw"
    venv_path: str = "/home/lishangli/repos/AutoResearchClaw/.venv"
    config_template: str = "config.arc.yaml"
    auto_run: bool = False
    require_confirmation: bool = True


@dataclass
class IntegrationConfig:
    researchclaw: ResearchClawConfig = field(default_factory=ResearchClawConfig)


@dataclass
class IdeasScoringConfig:
    novelty_weight: float = 0.30
    feasibility_weight: float = 0.25
    impact_weight: float = 0.20
    evidence_weight: float = 0.15
    timing_weight: float = 0.10


@dataclass
class IdeasConfig:
    enabled: bool = True
    papers_per_idea: int = 5
    max_ideas_per_day: int = 10
    min_novelty_score: float = 0.6
    scoring: IdeasScoringConfig = field(default_factory=IdeasScoringConfig)


@dataclass
class ProjectConfig:
    name: str = "paperpulse"
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"


@dataclass
class PaperPulseConfig:
    """Main configuration class for PaperPulse."""
    project: ProjectConfig = field(default_factory=ProjectConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    document: DocumentConfig = field(default_factory=DocumentConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)
    ideas: IdeasConfig = field(default_factory=IdeasConfig)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperPulseConfig:
        """Create config from dictionary."""
        config = cls()
        
        if "project" in data:
            config.project = ProjectConfig(**data["project"])
        
        if "sources" in data:
            sources = data["sources"]
            if "arxiv" in sources:
                config.sources.arxiv = ArxivConfig(**sources["arxiv"])
            if "semantic_scholar" in sources:
                config.sources.semantic_scholar = SemanticScholarConfig(**sources["semantic_scholar"])
            if "papers_with_code" in sources:
                config.sources.papers_with_code = PapersWithCodeConfig(**sources["papers_with_code"])
        
        if "document" in data:
            doc = data["document"]
            config.document = DocumentConfig(
                prefer_latex_source=doc.get("prefer_latex_source", True),
                pdf=PDFConfig(**doc.get("pdf", {})),
                converter=ConverterConfig(**doc.get("converter", {})),
            )
        
        if "llm" in data:
            config.llm = LLMConfig(**data["llm"])
        
        if "scheduler" in data:
            config.scheduler = SchedulerConfig(**data["scheduler"])
        
        if "obsidian" in data:
            obs = data["obsidian"]
            folders = obs.get("folders", {})
            config.obsidian = ObsidianConfig(
                enabled=obs.get("enabled", True),
                vault_path=obs.get("vault_path", ""),
                folders=ObsidianFoldersConfig(**folders) if folders else ObsidianFoldersConfig(),
            )
        
        if "storage" in data:
            config.storage = StorageConfig(**data["storage"])
        
        if "output" in data:
            config.output = OutputConfig(**data["output"])
        
        if "integration" in data:
            integ = data["integration"]
            if "researchclaw" in integ:
                config.integration.researchclaw = ResearchClawConfig(**integ["researchclaw"])
        
        if "ideas" in data:
            ideas = data["ideas"]
            scoring = ideas.get("scoring", {})
            config.ideas = IdeasConfig(
                enabled=ideas.get("enabled", True),
                papers_per_idea=ideas.get("papers_per_idea", 5),
                max_ideas_per_day=ideas.get("max_ideas_per_day", 10),
                min_novelty_score=ideas.get("min_novelty_score", 0.6),
                scoring=IdeasScoringConfig(**scoring) if scoring else IdeasScoringConfig(),
            )
        
        return config
    
    @classmethod
    def load(cls, path: str | Path) -> PaperPulseConfig:
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        return cls.from_dict(data)
    
    def get_obsidian_vault_path(self) -> Path:
        """Get the Obsidian vault path."""
        if self.obsidian.vault_path:
            return Path(self.obsidian.vault_path)
        return Path("./obsidian")


# Config search order
CONFIG_SEARCH_ORDER = [
    "config.yaml",
    "config.yml",
    "config.example.yaml",
]


def find_config_file() -> Path | None:
    """Find config file in search order."""
    for name in CONFIG_SEARCH_ORDER:
        path = Path(name)
        if path.exists():
            return path
    return None


def load_config(config_path: str | Path | None = None) -> PaperPulseConfig:
    """Load configuration from file or find default."""
    if config_path:
        return PaperPulseConfig.load(config_path)
    
    found = find_config_file()
    if found:
        return PaperPulseConfig.load(found)
    
    # Return default config if no file found
    return PaperPulseConfig()