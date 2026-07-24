"""Aggregate API v1 router -- mounts every domain router."""

from fastapi import APIRouter

from nivesh.ai_agents.router import router as ai_agents_router
from nivesh.api.v1.health import router as health_router
from nivesh.api.v1.version import router as version_router
from nivesh.companies.router import router as companies_router
from nivesh.market_data.router import router as market_data_router
from nivesh.portfolios.router import router as portfolios_router
from nivesh.research.router import router as research_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(version_router)
api_v1_router.include_router(companies_router)
api_v1_router.include_router(market_data_router)
api_v1_router.include_router(portfolios_router)
api_v1_router.include_router(research_router)
api_v1_router.include_router(ai_agents_router)
