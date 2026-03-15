"""
Skill: pdf_analyzer
Description: Analyze PDF documents — extract text, find keywords, summarize structure.
Uses: PyPDF2 or pdfplumber (fallback to subprocess pdftotext)
Author: Jane's Agent Builder
"""

import os

SKILL_NAME = "pdf_analyzer"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "Analyze PDF documents — extract text, find keywords, count pages"
SKILL_TOOLS = {
    "pdf_read": {
        "description": "Read and extract text from a PDF file",
        "args": {"path": "Path to the PDF file", "pages": "Optional: page range like '1-5' (default: all)"},
        "example": '{"tool": "pdf_read", "args": {"path": "C:/Users/Dator/Documents/contract.pdf"}}'
    },
    "pdf_info": {
        "description": "Get PDF metadata — pages, size, author, creation date",
        "args": {"path": "Path to the PDF file"},
        "example": '{"tool": "pdf_info", "args": {"path": "C:/Users/Dator/Documents/contract.pdf"}}'
    },
    "pdf_search": {
        "description": "Search for a keyword or phrase in a PDF",
        "args": {"path": "Path to PDF", "query": "Text to search for"},
        "example": '{"tool": "pdf_search", "args": {"path": "C:/Users/Dator/Documents/contract.pdf", "query": "payment terms"}}'
    }
}


def _extract_text_pypdf2(path: str, start_page: int = 0, end_page: int = None) -> str:
    """Extract text using PyPDF2"""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        pages = reader.pages
        if end_page is None:
            end_page = len(pages)
        
        text_parts = []
        for i in range(start_page, min(end_page, len(pages))):
            page_text = pages[i].extract_text() or ""
            text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
        
        return "\n\n".join(text_parts)
    except ImportError:
        return None


def _extract_text_pdfplumber(path: str, start_page: int = 0, end_page: int = None) -> str:
    """Extract text using pdfplumber"""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = pdf.pages
            if end_page is None:
                end_page = len(pages)
            
            text_parts = []
            for i in range(start_page, min(end_page, len(pages))):
                page_text = pages[i].extract_text() or ""
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
            
            return "\n\n".join(text_parts)
    except ImportError:
        return None


def _extract_text(path: str, start_page: int = 0, end_page: int = None) -> str:
    """Try multiple methods to extract text"""
    # Try PyPDF2 first
    result = _extract_text_pypdf2(path, start_page, end_page)
    if result is not None:
        return result
    
    # Try pdfplumber
    result = _extract_text_pdfplumber(path, start_page, end_page)
    if result is not None:
        return result
    
    # Fallback: suggest installation
    return ("Error: No PDF library installed.\n"
            "Install one: pip install PyPDF2\n"
            "Or: pip install pdfplumber")


def pdf_read(path: str, pages: str = "") -> str:
    """Read text from PDF"""
    if not os.path.exists(path):
        return f"File not found: {path}"
    
    start_page = 0
    end_page = None
    
    if pages:
        try:
            if '-' in pages:
                parts = pages.split('-')
                start_page = int(parts[0]) - 1
                end_page = int(parts[1])
            else:
                start_page = int(pages) - 1
                end_page = int(pages)
        except:
            pass
    
    text = _extract_text(path, start_page, end_page)
    
    if len(text) > 10000:
        text = text[:10000] + f"\n\n... (truncated, total {len(text)} chars. Use pages='1-5' to read specific pages)"
    
    return f"=== {os.path.basename(path)} ===\n{text}"


def pdf_info(path: str) -> str:
    """Get PDF metadata"""
    if not os.path.exists(path):
        return f"File not found: {path}"
    
    lines = [f"=== PDF Info: {os.path.basename(path)} ==="]
    lines.append(f"Size: {os.path.getsize(path) / 1024:.1f} KB")
    
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        lines.append(f"Pages: {len(reader.pages)}")
        
        meta = reader.metadata
        if meta:
            if meta.title:
                lines.append(f"Title: {meta.title}")
            if meta.author:
                lines.append(f"Author: {meta.author}")
            if meta.subject:
                lines.append(f"Subject: {meta.subject}")
            if meta.creator:
                lines.append(f"Creator: {meta.creator}")
            if hasattr(meta, 'creation_date') and meta.creation_date:
                lines.append(f"Created: {meta.creation_date}")
        
        # Check if encrypted
        if reader.is_encrypted:
            lines.append("⚠️ PDF is encrypted/password-protected")
        
    except ImportError:
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                lines.append(f"Pages: {len(pdf.pages)}")
                if pdf.metadata:
                    for k, v in pdf.metadata.items():
                        if v:
                            lines.append(f"{k}: {v}")
        except ImportError:
            lines.append("Install PyPDF2 or pdfplumber for detailed info: pip install PyPDF2")
    except Exception as e:
        lines.append(f"Error reading metadata: {e}")
    
    return "\n".join(lines)


def pdf_search(path: str, query: str) -> str:
    """Search for text in PDF"""
    if not os.path.exists(path):
        return f"File not found: {path}"
    
    text = _extract_text(path)
    if text.startswith("Error:"):
        return text
    
    query_lower = query.lower()
    lines = text.split('\n')
    
    results = []
    current_page = 0
    for line in lines:
        if line.startswith('--- Page '):
            try:
                current_page = int(line.split('Page ')[1].split(' ')[0])
            except:
                pass
        elif query_lower in line.lower():
            # Highlight match context
            idx = line.lower().find(query_lower)
            start = max(0, idx - 50)
            end = min(len(line), idx + len(query) + 50)
            context = line[start:end].strip()
            results.append(f"  Page {current_page}: ...{context}...")
    
    if not results:
        return f"'{query}' not found in {os.path.basename(path)}"
    
    header = f"=== Search: '{query}' in {os.path.basename(path)} ({len(results)} matches) ==="
    return header + "\n" + "\n".join(results[:30])


TOOLS = {
    "pdf_read": lambda args: pdf_read(args.get("path", ""), args.get("pages", "")),
    "pdf_info": lambda args: pdf_info(args.get("path", "")),
    "pdf_search": lambda args: pdf_search(args.get("path", ""), args.get("query", "")),
}
