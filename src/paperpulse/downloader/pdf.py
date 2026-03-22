"""PDF and LaTeX downloader."""

from __future__ import annotations

import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import PaperPulseConfig
from ..storage.database import Database
from ..storage.models import Paper, PaperStatus


class DocumentDownloader:
    """Download PDF and LaTeX source for papers."""

    # arXiv URLs
    ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}.pdf"
    ARXIV_LATEX_URL = "https://arxiv.org/e-print/{arxiv_id}"

    # Semantic Scholar PDF URL (via DOI or direct)
    S2_PDF_URL = "https://api.semanticscholar.org/{paper_id}"

    REQUEST_DELAY = 3.0
    _last_request_time: float = 0.0

    def __init__(self, config: PaperPulseConfig, db: Database):
        """Initialize downloader.

        Args:
            config: PaperPulse configuration
            db: Database instance
        """
        self.config = config
        self.db = db

        # Paths
        self.pdf_dir = Path(config.storage.pdf_dir)
        self.latex_dir = Path(config.storage.latex_dir)

        # Create directories
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.latex_dir.mkdir(parents=True, exist_ok=True)

    def download_paper(self, paper: Paper) -> tuple[bool, str, str]:
        """Download documents for a paper.

        Returns:
            Tuple of (success, pdf_path, latex_path)
        """
        pdf_path = ""
        latex_path = ""

        # Try LaTeX first for arXiv papers
        if paper.arxiv_id and self.config.document.prefer_latex_source:
            success, result = self.download_latex(paper.arxiv_id)
            if success:
                latex_path = result
                paper.latex_path = latex_path
                paper.status = PaperStatus.DOWNLOADED

        # Download PDF if needed
        if not pdf_path:
            success, result = self.download_pdf_for_paper(paper)
            if success:
                pdf_path = result
                paper.pdf_path = pdf_path
                if paper.status == PaperStatus.NEW:
                    paper.status = PaperStatus.DOWNLOADED

        # Update database
        if pdf_path or latex_path:
            self.db.update_paper(paper)

        return bool(pdf_path or latex_path), pdf_path, latex_path

    def download_papers(
        self,
        papers: list[Paper],
        max_concurrent: Optional[int] = None,
    ) -> dict[str, tuple[bool, str, str]]:
        """Download documents for multiple papers.

        Returns:
            Dict mapping paper_id to (success, pdf_path, latex_path)
        """
        max_concurrent = max_concurrent or self.config.document.pdf.max_concurrent
        results = {}

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(self.download_paper, paper): paper
                for paper in papers
            }

            for future in as_completed(futures):
                paper = futures[future]
                try:
                    result = future.result()
                    results[paper.paper_id] = result
                except Exception as e:
                    print(f"Error downloading {paper.paper_id}: {e}")
                    results[paper.paper_id] = (False, "", "")

        return results

    def download_pdf_for_paper(self, paper: Paper) -> tuple[bool, str]:
        """Download PDF for a paper."""
        if paper.arxiv_id:
            return self.download_arxiv_pdf(paper.arxiv_id)
        elif paper.doi:
            return self.download_doi_pdf(paper.doi, paper.paper_id)
        elif paper.url:
            return self.download_url_pdf(paper.url, paper.paper_id)
        else:
            return False, "No PDF source available"

    def download_arxiv_pdf(self, arxiv_id: str) -> tuple[bool, str]:
        """Download PDF from arXiv."""
        self._rate_limit()

        # Create dated subdirectory
        date_dir = self.pdf_dir / datetime.now().strftime("%Y/%m")
        date_dir.mkdir(parents=True, exist_ok=True)

        output_path = date_dir / f"{arxiv_id.replace('/', '_')}.pdf"
        if output_path.exists():
            return True, str(output_path)

        url = self.ARXIV_PDF_URL.format(arxiv_id=arxiv_id)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "PaperPulse/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.config.document.pdf.timeout_sec) as response:
                # Check size
                content_length = response.headers.get("Content-Length")
                if content_length:
                    size_mb = int(content_length) / (1024 * 1024)
                    if size_mb > self.config.document.pdf.max_size_mb:
                        return False, f"PDF too large ({size_mb:.1f}MB)"

                with open(output_path, "wb") as f:
                    f.write(response.read())

            return True, str(output_path)

        except urllib.error.HTTPError as e:
            return False, f"HTTP error {e.code}"
        except Exception as e:
            return False, str(e)

    def download_latex(self, arxiv_id: str) -> tuple[bool, str]:
        """Download LaTeX source from arXiv."""
        self._rate_limit()

        # Create dated subdirectory
        date_dir = self.latex_dir / datetime.now().strftime("%Y/%m")
        date_dir.mkdir(parents=True, exist_ok=True)

        extract_dir = date_dir / arxiv_id.replace("/", "_")
        if extract_dir.exists():
            return True, str(extract_dir)

        url = self.ARXIV_LATEX_URL.format(arxiv_id=arxiv_id)

        try:
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "PaperPulse/1.0"}
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    tmp.write(response.read())
                tmp_path = tmp.name

            # Extract
            extract_dir.mkdir(parents=True, exist_ok=True)

            with tarfile.open(tmp_path, "r:gz") as tar:
                tar.extractall(extract_dir)

            # Clean up temp file
            Path(tmp_path).unlink()

            return True, str(extract_dir)

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "LaTeX source not available"
            return False, f"HTTP error {e.code}"
        except tarfile.TarError as e:
            return False, f"Not a valid tar archive: {e}"
        except Exception as e:
            return False, str(e)

    def download_doi_pdf(self, doi: str, paper_id: str) -> tuple[bool, str]:
        """Try to download PDF via DOI (limited support)."""
        # Most DOI links don't provide direct PDF access
        # This is a placeholder for potential future implementation
        return False, "DOI PDF download not implemented"

    def download_url_pdf(self, url: str, paper_id: str) -> tuple[bool, str]:
        """Try to download PDF from URL."""
        if not url.endswith(".pdf") and "pdf" not in url.lower():
            return False, "URL does not appear to be a PDF"

        self._rate_limit()

        date_dir = self.pdf_dir / datetime.now().strftime("%Y/%m")
        date_dir.mkdir(parents=True, exist_ok=True)

        output_path = date_dir / f"{paper_id}.pdf"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "PaperPulse/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.config.document.pdf.timeout_sec) as response:
                with open(output_path, "wb") as f:
                    f.write(response.read())

            return True, str(output_path)

        except Exception as e:
            return False, str(e)

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()