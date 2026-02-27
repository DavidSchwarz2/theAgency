from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.adapters.github_client import GitHubClient, GitHubClientError
from app.schemas.registry import (
    AgentProfile,
    AgentProfileResponse,
    AgentWriteRequest,
    GitHubIssueResponse,
    PipelineTemplate,
    PipelineTemplateResponse,
    PipelineWriteRequest,
    RegistryConfig,
)
from app.services.agent_registry import AgentRegistry

router = APIRouter(prefix="/registry", tags=["registry"])


def get_registry(request: Request) -> AgentRegistry:
    """FastAPI dependency — reads from app.state.registry."""
    return request.app.state.registry


def get_github_client(request: Request) -> GitHubClient | None:
    """FastAPI dependency — reads from app.state.github_client (may be None)."""
    return getattr(request.app.state, "github_client", None)


@router.get("/agents", response_model=list[AgentProfileResponse])
async def list_agents(
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> list[AgentProfileResponse]:
    return [AgentProfileResponse.model_validate(a) for a in registry.agents()]


@router.post("/agents", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentWriteRequest,
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> AgentProfileResponse:
    if registry.get_agent(body.name) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Agent '{body.name}' already exists.")
    new_agent = AgentProfile(**body.model_dump())
    registry.save_agents(registry.agents() + [new_agent])
    return AgentProfileResponse.model_validate(new_agent)


@router.put("/agents/{name}", response_model=AgentProfileResponse)
async def update_agent(
    name: str,
    body: AgentWriteRequest,
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> AgentProfileResponse:
    if registry.get_agent(name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent '{name}' not found.")
    updated_agent = AgentProfile(**body.model_dump())
    registry.save_agents([updated_agent if a.name == name else a for a in registry.agents()])
    return AgentProfileResponse.model_validate(updated_agent)


@router.delete("/agents/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    name: str,
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> None:
    if registry.get_agent(name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent '{name}' not found.")
    remaining = [a for a in registry.agents() if a.name != name]
    # Validate referential integrity before writing
    try:
        RegistryConfig.model_validate(
            {"agents": [a.model_dump() for a in remaining], "pipelines": [p.model_dump() for p in registry.pipelines()]}
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    registry.save_agents(remaining)


@router.get("/pipelines", response_model=list[PipelineTemplateResponse])
async def list_pipelines(
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> list[PipelineTemplateResponse]:
    return [PipelineTemplateResponse.model_validate(p) for p in registry.pipelines()]


@router.post("/pipelines", response_model=PipelineTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    body: PipelineWriteRequest,
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> PipelineTemplateResponse:
    if registry.get_pipeline(body.name) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Pipeline '{body.name}' already exists.")
    new_pipeline = PipelineTemplate.model_validate(body.model_dump())
    all_pipelines = registry.pipelines() + [new_pipeline]
    try:
        RegistryConfig.model_validate(
            {
                "agents": [a.model_dump() for a in registry.agents()],
                "pipelines": [p.model_dump() for p in all_pipelines],
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    registry.save_pipelines(all_pipelines)
    return PipelineTemplateResponse.model_validate(new_pipeline)


@router.put("/pipelines/{name}", response_model=PipelineTemplateResponse)
async def update_pipeline(
    name: str,
    body: PipelineWriteRequest,
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> PipelineTemplateResponse:
    if registry.get_pipeline(name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pipeline '{name}' not found.")
    updated_pipeline = PipelineTemplate.model_validate(body.model_dump())
    updated = [updated_pipeline if p.name == name else p for p in registry.pipelines()]
    try:
        RegistryConfig.model_validate(
            {"agents": [a.model_dump() for a in registry.agents()], "pipelines": [p.model_dump() for p in updated]}
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    registry.save_pipelines(updated)
    return PipelineTemplateResponse.model_validate(updated_pipeline)


@router.delete("/pipelines/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    name: str,
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> None:
    if registry.get_pipeline(name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pipeline '{name}' not found.")
    registry.save_pipelines([p for p in registry.pipelines() if p.name != name])


@router.get("/github-issue", response_model=GitHubIssueResponse)
async def get_github_issue(
    repo: str,
    number: int,
    github_client: Annotated[GitHubClient | None, Depends(get_github_client)],
) -> GitHubIssueResponse:
    """Fetch a GitHub issue by repo and number for context preview.

    Returns 503 when no GitHub token is configured, 404 when the issue does not exist.
    """
    if github_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub token not configured. Set GITHUB_TOKEN in the backend .env file.",
        )
    try:
        issue = await github_client.get_issue(repo=repo, number=number)
    except GitHubClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"GitHub issue not found: {repo}#{number}"
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {exc}",
        ) from exc
    return GitHubIssueResponse(
        number=issue.number,
        title=issue.title,
        body=issue.body,
        labels=issue.labels,
    )
