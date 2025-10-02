"""
Веб-роуты для отображения страниц
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/studies", response_class=HTMLResponse)
async def studies(request: Request):
    """Страница со списком исследований"""
    return templates.TemplateResponse(
        "studies.html",
        {"request": request},
    )


@router.get("/studies/{study_id}", response_class=HTMLResponse)
async def study_detail(request: Request, study_id: int):
    """Детальная страница исследования"""
    return templates.TemplateResponse(
        "study_detail.html",
        {"request": request, "study_id": study_id},
    )


@router.get("/batches", response_class=HTMLResponse)
async def batches(request: Request):
    """Страница со списком батчей загрузки"""
    return templates.TemplateResponse(
        "batches.html",
        {"request": request},
    )


@router.get("/cleanup", response_class=HTMLResponse)
async def cleanup(request: Request):
    """Страница управления файлами"""
    return templates.TemplateResponse(
        "cleanup.html",
        {"request": request},
    )


@router.get("/batches/{batch_id}", response_class=HTMLResponse)
async def batch_detail(request: Request, batch_id: int):
    """Детальная страница батча загрузки"""
    return templates.TemplateResponse(
        "batch_detail.html",
        {"request": request, "batch_id": batch_id},
    )
