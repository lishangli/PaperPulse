"""MinerU PDF to Markdown converter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional


class MinerUConverter:
    """Convert PDF to Markdown using MinerU."""

    def __init__(
        self,
        output_dir: str | Path,
        method: str = "auto",
    ):
        """Initialize MinerU converter.

        Args:
            output_dir: Output directory for converted files
            method: Conversion method (auto, ocr, text)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.method = method

        # Check if MinerU is available
        self._mineru_available = self._check_mineru()

    def _check_mineru(self) -> bool:
        """Check if MinerU is installed."""
        try:
            import magic_pdf
            return True
        except ImportError:
            return False

    def convert(self, pdf_path: str | Path) -> tuple[bool, str]:
        """Convert PDF to Markdown.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (success, markdown_path or error_message)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return False, f"PDF not found: {pdf_path}"

        if not self._mineru_available:
            return self._convert_via_cli(pdf_path)

        return self._convert_python(pdf_path)

    def _convert_python(self, pdf_path: Path) -> tuple[bool, str]:
        """Convert using MinerU Python API."""
        try:
            from magic_pdf.data.data_reader_writer import FileBasedDataWriter
            from magic_pdf.data.dataset import PymuDocDataset

            # Output directory for this paper
            paper_output = self.output_dir / pdf_path.stem
            paper_output.mkdir(parents=True, exist_ok=True)

            # Read PDF
            ds = PymuDocDataset(str(pdf_path))

            # Analyze and convert
            if ds.classify() == "ocr":
                infer_result = ds.apply_ocr()
            else:
                infer_result = ds.apply()

            # Write Markdown
            writer = FileBasedDataWriter(str(paper_output))
            md_path = paper_output / f"{pdf_path.stem}.md"

            infer_result.dump_md(writer, md_path.name, "images")

            return True, str(md_path)

        except ImportError:
            return self._convert_via_cli(pdf_path)
        except Exception as e:
            return False, f"Conversion error: {e}"

    def _convert_via_cli(self, pdf_path: Path) -> tuple[bool, str]:
        """Convert using MinerU CLI (fallback)."""
        try:
            # Check if magic-pdf CLI is available
            result = subprocess.run(
                ["magic-pdf", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return False, "MinerU CLI not available. Install with: pip install mineru[all]"

        except FileNotFoundError:
            return False, "MinerU not installed. Install with: pip install mineru[all]"
        except Exception as e:
            return False, f"Error checking MinerU: {e}"

        # Run conversion
        try:
            output_dir = self.output_dir / pdf_path.stem

            cmd = [
                "magic-pdf",
                "-p", str(pdf_path),
                "-o", str(output_dir),
                "-m", self.method,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes max
            )

            if result.returncode != 0:
                return False, f"Conversion failed: {result.stderr}"

            # Find generated markdown
            md_files = list(output_dir.rglob("*.md"))
            if md_files:
                return True, str(md_files[0])

            return False, "No markdown file generated"

        except subprocess.TimeoutExpired:
            return False, "Conversion timeout"
        except Exception as e:
            return False, f"Conversion error: {e}"

    def batch_convert(
        self,
        pdf_paths: list[str | Path],
        max_workers: int = 1,
    ) -> dict[str, tuple[bool, str]]:
        """Convert multiple PDFs.

        Args:
            pdf_paths: List of PDF paths
            max_workers: Maximum concurrent conversions (usually 1 for MinerU)

        Returns:
            Dict mapping PDF path to (success, result)
        """
        results = {}

        for pdf_path in pdf_paths:
            pdf_path = Path(pdf_path)
            results[str(pdf_path)] = self.convert(pdf_path)

        return results

    def is_available(self) -> bool:
        """Check if converter is available."""
        return self._mineru_available

    @staticmethod
    def install_instructions() -> str:
        """Get installation instructions."""
        return """
To install MinerU:

    pip install mineru[all]

Or for minimal installation:

    pip install mineru

For GPU support, ensure CUDA is available.
See: https://github.com/opendatalab/MinerU
"""