from typing import Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

@app.post("/lemmatize", openapi_extra=_TEXT_BODY_OPENAPI)
async def lemmatize(request: Request) -> Dict[str, int]:
    return extract_lemmas(await _read_text(request))

@app.post("/word-stats", response_model=List[WordStat], openapi_extra=_TEXT_BODY_OPENAPI)
async def word_stats(request: Request):
    return extract_word_stats(await _read_text(request))
