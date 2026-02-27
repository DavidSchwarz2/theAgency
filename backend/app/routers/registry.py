from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.schemas.registry import AgentProfileResponse, PipelineTemplateResponse
from app.services.agent_registry import AgentRegistry

router = APIRouter(prefix="/registry", tags=["registry"])


def get_registry(request: Request) -> AgentRegistry:
    """FastAPI dependency — reads from app.state.registry."""
    return request.app.state.registry


@router.get("/agents", response_model=list[AgentProfileResponse])
async def list_agents(
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> list[AgentProfileResponse]:
    return [AgentProfileResponse.model_validate(a) for a in registry.agents()]


@router.get("/pipelines", response_model=list[PipelineTemplateResponse])
async def list_pipelines(
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> list[PipelineTemplateResponse]:
    return [PipelineTemplateResponse.model_validate(p) for p in registry.pipelines()]
