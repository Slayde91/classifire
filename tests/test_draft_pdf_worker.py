from __future__ import annotations

import pymupdf
import pytest

from classifire.services.draft_pdf_intake import _process
from classifire.services.draft_scope import DraftScopeError


@pytest.mark.parametrize("kind", ["invalid", "encrypted", "embedded", "too_many_pages"])
def test_unsupported_pdf_never_returns_normalized_document(kind):
    if kind == "invalid":
        data = b"%PDF-invalid synthetic data"
    else:
        with pymupdf.open() as pdf:
            for _ in range(51 if kind == "too_many_pages" else 1):
                pdf.new_page()
            if kind == "embedded":
                pdf.embfile_add("synthetic.txt", b"synthetic")
            data = (
                pdf.tobytes(
                    encryption=pymupdf.PDF_ENCRYPT_AES_256,
                    owner_pw="synthetic",
                    user_pw="synthetic",
                )
                if kind == "encrypted"
                else pdf.tobytes()
            )
    with pytest.raises(DraftScopeError, match="PDF_PROCESSING_FAILED"):
        _process(data)
