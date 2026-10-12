"""Support and legal documents router — API-only JSON responses"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/support", tags=["support"])

STATIC_DIR = Path(__file__).parent.parent / "static" / "support"

AVAILABLE_DOCS = {
    "termsofservice": "Terms of Service",
    "privacypolicy": "Privacy Policy",
    "fairuse": "Fair Use Policy",
    "license": "License",
}


@router.get("")
async def list_support_docs():
    """List all available support/legal documents."""
    return {
        "documents": [{"id": doc_id, "title": title} for doc_id, title in AVAILABLE_DOCS.items()]
    }


@router.get("/{doc}")
async def get_support_doc(doc: str):
    """Return a support/legal document as JSON content."""
    doc_map = {
        "termsofservice": "termsofservice.html",
        "privacypolicy": "privacypolicy.html",
        "fairuse": "fairuse.html",
        "license": "license.html",
    }

    if doc not in doc_map:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{doc}' not found. Available: {', '.join(AVAILABLE_DOCS.keys())}",
        )

    file_path = STATIC_DIR / doc_map[doc]

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on server")

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        return {"id": doc, "title": AVAILABLE_DOCS[doc], "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading document: {e!s}")
