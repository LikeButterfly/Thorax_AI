"""
API модули
"""

from app.api import healthcheck
from app.api.studies import router as studies_router

__all__ = ["studies_router", "healthcheck"]
