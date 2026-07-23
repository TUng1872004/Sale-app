from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.web import router
from app.auth import LoginRequired
from app.core.config import get_settings
from app.db import init_db
from app.rec.service import load_artifact


BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    load_artifact()
    yield


app = FastAPI(title="Sales Management Demo", lifespan=lifespan)


@app.exception_handler(LoginRequired)
async def redirect_unauthenticated(request: Request, _: LoginRequired) -> RedirectResponse:
    request.session.pop("sale_id", None)
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret,
    session_cookie="sales_session",
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(router)
