"""Isolated parser subprocess. Private document bytes enter through stdin."""

import base64
import json
import os
import sys

os.environ.setdefault("OMP_THREAD_LIMIT", "1")
from .parsers import parse_document, ParseError
from .ocr import configured_ocr_provider
from .providers import OCRUnavailable

if __name__ == "__main__":
    payload = json.loads(sys.stdin.buffer.read())
    try:
        chunks = parse_document(
            payload["name"],
            base64.b64decode(payload["data"]),
            ocr=configured_ocr_provider(),
        )
        result = {"chunks": chunks}
    except (ParseError, OCRUnavailable) as error:
        result = {"error": str(error)}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
