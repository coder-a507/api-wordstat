import hashlib
import secrets
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from app.nlp import TextTooLongError, extract_lemmas, extract_word_stats

app = FastAPI(title="api-eng")


class WordStat(BaseModel):
    lemma: str
    pos: str
    count: int

# Разрешаем запросы с сайта
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # лучше указать конкретный домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(TextTooLongError)
def handle_text_too_long(request: Request, exc: TextTooLongError) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": str(exc)})

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

# The text endpoints require an `X-Api-Token` header. Only the token's SHA-256
# hash is stored, in `api_token.sha256` (committed: the hosting gets code only
# from git, and a hash of a long random token is safe to publish). Create or
# rotate the token with `new_token.py`. No hash file means every request is
# refused with 503, so a missing file can't silently leave the API open.
API_TOKEN_HASH_FILE = Path(__file__).resolve().parent.parent / "api_token.sha256"

_api_token_header = APIKeyHeader(name="X-Api-Token", auto_error=False)

def _expected_token_hash() -> Optional[str]:
    try:
        value = API_TOKEN_HASH_FILE.read_text(encoding="utf-8").strip().lower()
    except FileNotFoundError:
        return None
    return value or None

def require_api_token(token: Optional[str] = Security(_api_token_header)) -> None:
    expected = _expected_token_hash()
    if expected is None:
        raise HTTPException(status_code=503, detail="API token is not configured on the server")
    actual = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    if not token or not secrets.compare_digest(actual, expected):
        raise HTTPException(status_code=401, detail="missing or invalid X-Api-Token header")

# The text endpoints read the raw body themselves instead of declaring
# `Body(media_type="text/plain")`: FastAPI 0.103 (the last release for
# Python 3.7) parses a body sent without a Content-Type header as JSON, so
# plain text sent that way would be rejected with 422. This OpenAPI snippet
# keeps the plain-text textarea in Swagger UI.
_TEXT_BODY_OPENAPI = {
    "requestBody": {
        "required": False,
        "content": {"text/plain": {"schema": {"type": "string"}}},
    }
}

async def _read_text(request: Request) -> str:
    try:
        return (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="request body is not valid UTF-8")

@app.post("/lemmatize", openapi_extra=_TEXT_BODY_OPENAPI,
          dependencies=[Depends(require_api_token)])
async def lemmatize(request: Request) -> Dict[str, int]:
    return extract_lemmas(await _read_text(request))

@app.post("/word-stats", response_model=List[WordStat], openapi_extra=_TEXT_BODY_OPENAPI,
          dependencies=[Depends(require_api_token)])
async def word_stats(request: Request):
    return extract_word_stats(await _read_text(request))
