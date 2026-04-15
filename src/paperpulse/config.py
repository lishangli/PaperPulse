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
class DomainConfig:
    """Configuration for a research domain."""
    name: str = ""
    weight: int = 10  # Percentage weight
    categories: list[str] = field(default_factory=list)  # arXiv categories
    keywords: list[str] = field(default_factory=list)  # Search keywords


@dataclass
class DailyReadingConfig:
    """Configuration for daily automated paper reading."""
    enabled: bool = True
    total_papers: int = 10  # Total papers to read per day
    domains: list[DomainConfig] = field(default_factory=lambda: [
        DomainConfig(name="math", weight=10, categories=["math.NA", "math.CO", "math.ST", "math.IT"]),
        DomainConfig(name="ai_theory", weight=30, categories=["cs.AI", "cs.LG", "cs.CL"]),
        DomainConfig(name="ai_os_compiler", weight=30, categories=["cs.AR", "cs.OS"], keywords=["compiler", "operating system", "OS", "systems"]),
        DomainConfig(name="ai_infrastructure", weight=30, categories=["cs.DC", "cs.NI"], keywords=["infrastructure", "distributed", "cloud", "GPU", "cluster"]),
    ])


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
    # Backend selection: "openai" for direct API, or ACP backend name
    # Supported ACP backends: "pi", "claude-code", "codex-cli", "copilot-cli", "gemini-cli"
    backend: str = "openai"
    
    # OpenAI API settings (used when backend == "openai")
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    
    # Model selection (works for both OpenAI and ACP backends)
    # For OpenAI: "gpt-4o", "gpt-4o-mini", etc.
    # For ACP backends: use provider/model format, e.g., "anthropic/claude-sonnet-4-20250514"
    primary_model: str = "gpt-4o"
    fallback_model: str = "gpt-4o-mini"
    
    # ACP-specific settings (used when backend != "openai")
    thinking_level: str = "medium"  # off, minimal, low, medium, high, xhigh
    acp_command: str = ""  # Custom command to spawn agent (optional)
    acp_timeout_sec: int = 180  # Timeout for agent responses (longer for research)
    acp_use_session: bool = False  # Enable session persistence
    acp_cwd: str = ""  # Working directory for agent
    acp_extra_args: list[str] = field(default_factory=list)  # Additional CLI arguments
    
    def get_api_key(self) -> str:
        """Get API key from config or environment."""
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")
    
    def is_acp_backend(self) -> bool:
        """Check if using an ACP-compatible backend."""
        return self.backend != "openai"
    
    def get_acp_config(self):
        """Get ACPConfig for ACP backends."""
        from .analysis.acp_client import ACPConfig
        return ACPConfig(
            backend=self.backend,
            model=self.primary_model,
            thinking_level=self.thinking_level,
            command=self.acp_command,
            timeout_sec=self.acp_timeout_sec,
            use_session=self.acp_use_session,
            cwd=self.acp_cwd,
            extra_args=self.acp_extra_args,
        )


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
class NotionCategoryRuleConfig:
    """Configuration for a single category detection rule."""
    category: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass
class NotionCategoryRulesConfig:
    """Configuration for category auto-detection rules."""
    default: str = "Research"
    rules: list[NotionCategoryRuleConfig] = field(default_factory=lambda: [
        NotionCategoryRuleConfig(category="AI", keywords=['ai', 'llm', 'agent', 'neural', 'deep', 'machine learning', 'benchmark']),
        NotionCategoryRuleConfig(category="Compiler", keywords=['compiler', 'cgra', 'scheduling', 'optimization', 'hardware', 'modulo']),
        NotionCategoryRuleConfig(category="Math", keywords=['math', 'proof', 'equation', 'theorem', 'hyperbolic', 'particle', 'plasma']),
        NotionCategoryRuleConfig(category="System", keywords=['system', 'os', 'infrastructure', 'distributed']),
    ])


@dataclass
class NotionConfig:
    """Configuration for Notion sync using notionary."""
    enabled: bool = False
    api_key_env: str = "NOTION_API_KEY"
    api_key: str = ""  # Or read from environment
    # Target page/database to sync reports to
    # Can be page title (will search) or page ID
    target_page: str = ""  # e.g., "PaperPulse Reports" or UUID
    target_database: str = ""  # e.g., "Research Papers" or UUID
    # Sync options
    create_new_pages: bool = True  # Create new pages instead of appending
    clear_previous: bool = False  # Clear previous pages with same title
    # Rate limiting
    rate_limit_delay: float = 0.5  # Delay between API calls (seconds)
    
    # Category auto-detection rules
    category_rules: NotionCategoryRulesConfig = field(default_factory=NotionCategoryRulesConfig)
    # Common tags for extraction
    common_tags: list[str] = field(default_factory=lambda: [
        'AI', 'LLM', 'Agent', 'Compiler', 'CGRA', 'Scheduling',
        'Optimization', 'Research', 'Survey', 'Benchmark', 'Math',
        'Neural', 'Deep Learning', 'Plasma', 'Hyperbolic'
    ])
    # Property settings
    summary_max_length: int = 150
    max_tags_per_page: int = 5
    
    def get_api_key(self) -> str:
        """Get API key from config or environment."""
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")
    
    def detect_category(self, title: str) -> str:
        """Detect category from title using rules."""
        title_lower = title.lower()
        for rule in self.category_rules.rules:
            for keyword in rule.keywords:
                if keyword.lower() in title_lower:
                    return rule.category
        return self.category_rules.default
    
    def extract_tags(self, title: str) -> list[str]:
        """Extract tags from title using common_tags."""
        title_lower = title.lower()
        tags = []
        for tag in self.common_tags:
            if tag.lower() in title_lower:
                tags.append(tag)
        if not tags:
            tags = ['Research']
        return tags[:self.max_tags_per_page]


@dataclass
class SynthesisConfig:
    """Configuration for synthesis report generation."""
    enabled: bool = True
    max_content_chars: int = 50000  # ~12k tokens
    llm_call_interval: float = 10.0  # Seconds between LLM calls
    filename_format: str = "{arxiv_id}_synthesis_{date}"


@dataclass
class ArxivAPIConfig:
    """Configuration for arXiv API."""
    rate_limit_wait: float = 3.0  # Seconds between requests
    retry_count: int = 3
    retry_wait: float = 5.0  # Seconds before retry


@dataclass
class CLIDefaultsConfig:
    """Default values for CLI commands."""
    collect_days: int = 7
    collect_limit: int = 20
    convert_mode: str = "auto"
    convert_pdf_dir: str = "data/pdfs"
    analyze_limit: int = 10
    synthesis_days: int = 1
    synthesis_limit: int = 5
    ideas_num: int = 5
    ideas_min_score: float = 0.6
    list_limit: int = 10
    notion_rate_limit: float = 0.5
    notion_pattern: str = "*.md"


@dataclass
class PathsConfig:
    """Configuration for paths (supports environment variables)."""
    paperpulse_dir: str = "."  # Relative to config file
    log_dir: str = "./logs"
    bin_dir: str = "${HOME}/.local/bin"
    
    def resolve_path(self, path: str, base_dir: Path | None = None) -> Path:
        """Resolve path with environment variable expansion."""
        import os
        expanded = os.path.expandvars(path)
        if base_dir and not Path(expanded).is_absolute():
            return base_dir / expanded
        return Path(expanded)


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
    daily_reading: DailyReadingConfig = field(default_factory=DailyReadingConfig)
    notion: NotionConfig = field(default_factory=NotionConfig)
    # New configuration sections
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)
    arxiv_api: ArxivAPIConfig = field(default_factory=ArxivAPIConfig)
    cli_defaults: CLIDefaultsConfig = field(default_factory=CLIDefaultsConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    
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
        
        if "daily_reading" in data:
            dr = data["daily_reading"]
            domains = []
            for domain_data in dr.get("domains", []):
                domains.append(DomainConfig(
                    name=domain_data.get("name", ""),
                    weight=domain_data.get("weight", 10),
                    categories=domain_data.get("categories", []),
                    keywords=domain_data.get("keywords", []),
                ))
            config.daily_reading = DailyReadingConfig(
                enabled=dr.get("enabled", True),
                total_papers=dr.get("total_papers", 10),
                domains=domains if domains else None,  # Use default if empty
            )
        
        if "notion" in data:
            notion_data = data["notion"]
            
            # Parse category_rules
            category_rules_data = notion_data.get("category_rules", {})
            rules_list = []
            for rule_data in category_rules_data.get("rules", []):
                rules_list.append(NotionCategoryRuleConfig(
                    category=rule_data.get("category", ""),
                    keywords=rule_data.get("keywords", []),
                ))
            category_rules = NotionCategoryRulesConfig(
                default=category_rules_data.get("default", "Research"),
                rules=rules_list if rules_list else None,
            )
            
            config.notion = NotionConfig(
                enabled=notion_data.get("enabled", False),
                api_key_env=notion_data.get("api_key_env", "NOTION_API_KEY"),
                api_key=notion_data.get("api_key", ""),
                target_page=notion_data.get("target_page", ""),
                target_database=notion_data.get("target_database", ""),
                create_new_pages=notion_data.get("create_new_pages", True),
                clear_previous=notion_data.get("clear_previous", False),
                rate_limit_delay=notion_data.get("rate_limit_delay", 0.5),
                category_rules=category_rules,
                common_tags=notion_data.get("common_tags", config.notion.common_tags),
                summary_max_length=notion_data.get("summary_max_length", 150),
                max_tags_per_page=notion_data.get("max_tags_per_page", 5),
            )
        
        # Parse synthesis config
        if "synthesis" in data:
            config.synthesis = SynthesisConfig(**data["synthesis"])
        
        # Parse arxiv_api config
        if "arxiv_api" in data:
            config.arxiv_api = ArxivAPIConfig(**data["arxiv_api"])
        
        # Parse cli_defaults config
        if "cli_defaults" in data:
            config.cli_defaults = CLIDefaultsConfig(**data["cli_defaults"])
        
        # Parse paths config
        if "paths" in data:
            config.paths = PathsConfig(**data["paths"])
        
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