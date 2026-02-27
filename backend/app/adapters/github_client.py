"""HTTP adapter for the GitHub REST API v3."""

import httpx

from app.adapters.github_models import GitHubIssue


class GitHubClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    _BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.AsyncClient(base_url=self._BASE_URL, headers=headers)

    async def close(self) -> None:
        if not self._http.is_closed:
            await self._http.aclose()

    async def get_issue(self, repo: str, number: int) -> GitHubIssue:
        """Fetch a single GitHub issue.

        Args:
            repo: Repository in ``owner/repo`` format, e.g. ``DavidSchwarz2/theAgency``.
            number: Issue number.

        Returns:
            A GitHubIssue with number, title, body, and labels.

        Raises:
            GitHubClientError: On any non-2xx response.
        """
        resp = await self._http.get(f"/repos/{repo}/issues/{number}")
        self._raise_for_status(resp)
        data = resp.json()
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            labels=[label["name"] for label in data.get("labels", [])],
        )

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.is_error:
            raise GitHubClientError(
                f"GitHub API error {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
