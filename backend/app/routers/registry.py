from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.adapters.github_client import GitHubClient, GitHubClientError
from app.schemas.registry import AgentProfileResponse, GitHubIssueResponse, PipelineTemplateResponse
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


@router.get("/pipelines", response_model=list[PipelineTemplateResponse])
async def list_pipelines(
    registry: Annotated[AgentRegistry, Depends(get_registry)],
) -> list[PipelineTemplateResponse]:
    return [PipelineTemplateResponse.model_validate(p) for p in registry.pipelines()]


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
            )
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
