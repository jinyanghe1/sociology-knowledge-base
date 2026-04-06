"""Document Parser - Multi-format document parsing with optimized chunking.

Supports: PDF, Word (DOC/DOCX), PowerPoint (PPT/PPTX), Markdown, Text
Optimized for large knowledge bases with efficient text extraction.
"""

import re
import uuid
from pathlib import Path
from typing import List, Optional


class DocumentParser:
    """High-performance document parser with semantic chunking."""

    # Optimized for sociology texts: larger chunks preserve complete arguments
    CHUNK_SIZE = 3000  # ~1000 中文 tokens, 保留完整论述
    CHUNK_OVERLAP = 300  # Increased overlap for continuity
    MIN_CHUNK_SIZE = 200  # Minimum meaningful chunk

    SUPPORTED_EXTENSIONS = {
        '.pdf': 'pdf',
        '.doc': 'doc',
        '.docx': 'docx',
        '.ppt': 'ppt',
        '.pptx': 'pptx',
        '.md': 'markdown',
        '.markdown': 'markdown',
        '.txt': 'text',
        '.rst': 'text',
        '.html': 'html',
        '.htm': 'html',
    }

    @classmethod
    def get_file_type(cls, file_path: str) -> Optional[str]:
        """Get file type from extension."""
        ext = Path(file_path).suffix.lower()
        return cls.SUPPORTED_EXTENSIONS.get(ext)

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """Check if file type is supported."""
        return cls.get_file_type(file_path) is not None

    @classmethod
    def _clean_text(cls, text: str) -> str:
        """Clean extracted text for better embedding quality.

        Removes control characters, normalizes whitespace, and filters
        page number artifacts that degrade chunk quality.
        """
        # Remove control characters (0x00-0x1f except 0x09 tab, 0x0a newline, 0x0d return)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

        # Normalize multiple spaces/newlines to single
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple tabs/spaces -> single space
        text = re.sub(r'\n{3,}', '\n\n', text)  # 3+ newlines -> 2 newlines

        # Remove page number artifacts (e.g., "第 5 页", "Page 5", "- 5 -")
        text = re.sub(r'第\s*\d+\s*页', '', text)
        text = re.sub(r'Page\s+\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'-\s*\d+\s*-', '', text)

        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)

        return text.strip()

    def parse(self, file_path: str, file_type: Optional[str] = None) -> List[dict]:
        """Parse document into chunks.
        
        Args:
            file_path: Path to the document
            file_type: Optional file type override
            
        Returns:
            List of chunk dictionaries
        """
        if file_type is None:
            file_type = self.get_file_type(file_path)
            
        if file_type is None:
            raise ValueError(f"Unsupported file type: {file_path}")

        # Route to appropriate parser
        parsers = {
            'pdf': self._parse_pdf,
            'doc': self._parse_doc,
            'docx': self._parse_docx,
            'ppt': self._parse_ppt,
            'pptx': self._parse_pptx,
            'markdown': self._parse_markdown,
            'text': self._parse_text,
            'html': self._parse_html,
        }
        
        parser = parsers.get(file_type)
        if not parser:
            raise ValueError(f"No parser available for type: {file_type}")
            
        return parser(file_path)

    def _parse_pdf(self, file_path: str) -> List[dict]:
        """Parse PDF with page-aware chunking."""
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber is required. Install: pip install pdfplumber")

        chunks = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    # Add page context to chunks
                    page_chunks = self._chunk_text(
                        text, 
                        file_path, 
                        metadata={"page": page_num}
                    )
                    chunks.extend(page_chunks)
        return chunks

    def _parse_docx(self, file_path: str) -> List[dict]:
        """Parse DOCX with paragraph-aware chunking."""
        try:
            from docx import Document
        except ImportError:
            raise ImportError("python-docx is required. Install: pip install python-docx")

        doc = Document(file_path)
        full_text = []
        
        # Extract text with structure
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text)
        
        # Also extract from tables
        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text for cell in row.cells if cell.text.strip()]
                if row_text:
                    full_text.append(" | ".join(row_text))
        
        text = "\n".join(full_text)
        return self._chunk_text(text, file_path, metadata={"format": "docx"})

    def _parse_doc(self, file_path: str) -> List[dict]:
        """Parse DOC using antiword or textract fallback."""
        try:
            # Try textract first (handles many formats)
            import textract
            text = textract.process(file_path).decode('utf-8', errors='ignore')
        except ImportError:
            # Fallback: try antiword for .doc files
            import subprocess
            try:
                result = subprocess.run(
                    ['antiword', file_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                text = result.stdout
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise ImportError(
                    "Cannot parse .doc files. Install: pip install textract or antiword"
                )
        
        return self._chunk_text(text, file_path, metadata={"format": "doc"})

    def _parse_pptx(self, file_path: str) -> List[dict]:
        """Parse PPTX with slide-aware chunking."""
        try:
            from pptx import Presentation
        except ImportError:
            raise ImportError("python-pptx is required. Install: pip install python-pptx")

        prs = Presentation(file_path)
        chunks = []
        
        for slide_num, slide in enumerate(prs.slides, 1):
            slide_texts = []
            
            # Extract text from all shapes
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_texts.append(shape.text)
            
            if slide_texts:
                text = "\n".join(slide_texts)
                slide_chunks = self._chunk_text(
                    text,
                    file_path,
                    metadata={"slide": slide_num}
                )
                chunks.extend(slide_chunks)
        
        return chunks

    def _parse_ppt(self, file_path: str) -> List[dict]:
        """Parse PPT using textract fallback."""
        try:
            import textract
            text = textract.process(file_path).decode('utf-8', errors='ignore')
        except ImportError:
            raise ImportError("textract is required for .ppt files. Install: pip install textract")
        
        return self._chunk_text(text, file_path, metadata={"format": "ppt"})

    def _parse_markdown(self, file_path: str) -> List[dict]:
        """Parse Markdown preserving structure."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Convert to plain text while preserving structure
        # Simple header preservation
        lines = content.split('\n')
        structured_text = []
        
        for line in lines:
            # Preserve headers as section markers
            if line.startswith('#'):
                structured_text.append(f"\n{line}\n")
            else:
                structured_text.append(line)
        
        text = '\n'.join(structured_text)
        return self._chunk_text(text, file_path, metadata={"format": "markdown"})

    def _parse_text(self, file_path: str) -> List[dict]:
        """Parse plain text files."""
        with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
            text = f.read()
        return self._chunk_text(text, file_path, metadata={"format": "text"})

    def _parse_html(self, file_path: str) -> List[dict]:
        """Parse HTML files."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            # Fallback to regex
            return self._parse_text(file_path)
        
        with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
        
        return self._chunk_text(text, file_path, metadata={"format": "html"})

    def _chunk_text(self, text: str, source: str, metadata: Optional[dict] = None) -> List[dict]:
        """Smart text chunking with semantic boundaries.

        Optimized for retrieval efficiency:
        - Respects paragraph boundaries when possible
        - Maintains context with overlap
        - Filters out too-small chunks
        - Cleans text before chunking
        """
        if not text or not text.strip():
            return []

        # Clean text before chunking
        text = self._clean_text(text)
        
        chunks = []
        chunk_index = 0
        
        # Split into paragraphs first
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        
        current_chunk = ""
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para)
            
            # If adding this paragraph exceeds chunk size, finalize current chunk
            if current_size + para_size > self.CHUNK_SIZE and current_size >= self.MIN_CHUNK_SIZE:
                chunk_meta = {"source": source, "chunk_index": chunk_index}
                if metadata:
                    chunk_meta.update(metadata)
                
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "content": current_chunk.strip(),
                    "chunk_index": chunk_index,
                    "metadata": chunk_meta
                })
                chunk_index += 1
                
                # Start new chunk with overlap
                if len(current_chunk) > self.CHUNK_OVERLAP:
                    current_chunk = current_chunk[-self.CHUNK_OVERLAP:] + "\n" + para
                else:
                    current_chunk = para
                current_size = len(current_chunk)
            else:
                if current_chunk:
                    current_chunk += "\n"
                current_chunk += para
                current_size += para_size + 1
        
        # Don't forget the last chunk
        if current_chunk.strip() and len(current_chunk) >= self.MIN_CHUNK_SIZE:
            chunk_meta = {"source": source, "chunk_index": chunk_index}
            if metadata:
                chunk_meta.update(metadata)
            
            chunks.append({
                "id": str(uuid.uuid4()),
                "content": current_chunk.strip(),
                "chunk_index": chunk_index,
                "metadata": chunk_meta
            })
        
        return chunks

    def parse_batch(self, file_paths: List[str], progress_callback=None) -> dict:
        """Parse multiple documents with progress tracking.
        
        Args:
            file_paths: List of file paths to parse
            progress_callback: Optional callback(current, total, filename)
            
        Returns:
            Dict with 'results' and 'errors'
        """
        results = {}
        errors = {}
        
        for i, path in enumerate(file_paths):
            if progress_callback:
                progress_callback(i + 1, len(file_paths), path)
            
            try:
                if self.is_supported(path):
                    chunks = self.parse(path)
                    results[path] = chunks
                else:
                    errors[path] = "Unsupported file type"
            except Exception as e:
                errors[path] = str(e)
        
        return {"results": results, "errors": errors}
