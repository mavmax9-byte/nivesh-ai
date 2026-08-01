"""Aggregate API v1 router -- mounts every domain router."""

from fastapi import APIRouter

from nivesh.ai_agents.router import fundamental_router as ai_agents_fundamental_router
from nivesh.ai_agents.router import news_sentiment_router as ai_agents_news_sentiment_router
from nivesh.ai_agents.router import risk_router as ai_agents_risk_router
from nivesh.ai_agents.router import router as ai_agents_router
from nivesh.ai_agents.router import technical_router as ai_agents_technical_router
from nivesh.ai_agents.router import valuation_router as ai_agents_valuation_router
from nivesh.api.v1.health import router as health_router
from nivesh.api.v1.version import router as version_router
from nivesh.companies.router import router as companies_router
from nivesh.corporate_filings.router import router as corporate_filings_router
from nivesh.document_intelligence.router import router as document_intelligence_router
from nivesh.financials.router import router as financials_router
from nivesh.knowledge_layer.router import router as knowledge_layer_router
from nivesh.market_data.router import router as market_data_router
from nivesh.market_universe.router import router as market_universe_router
from nivesh.news_intelligence.router import router as news_intelligence_router
from nivesh.portfolio_planner.router import router as portfolio_planner_router
from nivesh.portfolios.router import router as portfolios_router
from nivesh.research.router import router as research_router
from nivesh.retrieval_engine.router import router as retrieval_engine_router
from nivesh.technical_intelligence.router import router as technical_intelligence_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(version_router)
api_v1_router.include_router(companies_router)
api_v1_router.include_router(market_data_router)
api_v1_router.include_router(financials_router)
api_v1_router.include_router(corporate_filings_router)
api_v1_router.include_router(document_intelligence_router)
api_v1_router.include_router(news_intelligence_router)
api_v1_router.include_router(technical_intelligence_router)
api_v1_router.include_router(knowledge_layer_router)
api_v1_router.include_router(portfolios_router)
api_v1_router.include_router(portfolio_planner_router)
api_v1_router.include_router(market_universe_router)
api_v1_router.include_router(research_router)
api_v1_router.include_router(retrieval_engine_router)
api_v1_router.include_router(ai_agents_router)
api_v1_router.include_router(ai_agents_fundamental_router)
api_v1_router.include_router(ai_agents_technical_router)
api_v1_router.include_router(ai_agents_valuation_router)
api_v1_router.include_router(ai_agents_news_sentiment_router)
api_v1_router.include_router(ai_agents_risk_router)
