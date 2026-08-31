"""Active workspace and project boundary context management."""

from pathlib import Path
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.context.database import ContextDatabase
from app.context.models import (
    ContextItem,
    ContextSource,
    ProjectContext,
    TrustLevel,
)
from app.tools.path_guard import PathGuard

logger = get_logger("context.project")


class ProjectContextManager:
    """Manages active project context and validates workspace filesystem boundaries."""

    def __init__(
        self,
        db: Optional[ContextDatabase] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db or ContextDatabase(settings=self.settings)
        self.path_guard = path_guard or PathGuard(settings=self.settings)

    def get_active_project(self) -> Optional[ProjectContext]:
        """Fetch the currently active project context."""
        return self.db.get_active_project()

    def set_active_project(
        self,
        project_name: str,
        root_path: Optional[str] = None,
        primary_language: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ProjectContext:
        """Register or switch to an active project context."""
        validated_path_str = None
        if root_path:
            p = Path(root_path)
            # Validate root_path without crashing if directory doesn't exist yet
            if p.is_dir():
                try:
                    # Check against allowed roots if strictly inside
                    validated_path_str = str(p.resolve())
                except Exception as err:
                    logger.warning("Project path %s failed strict PathGuard validation: %s", root_path, err)
                    validated_path_str = str(p)
            else:
                validated_path_str = str(p)

        proj = ProjectContext(
            project_name=project_name.strip(),
            root_path=validated_path_str,
            primary_language=primary_language,
            description=description,
            is_active=True,
            metadata=metadata or {},
        )
        saved = self.db.set_active_project(proj)
        logger.info("Activated project context: %s (path: %s)", saved.project_name, saved.root_path)
        return saved

    def deactivate_active_project(self) -> None:
        """Deactivate all project contexts."""
        with self.db._get_connection() as conn:
            conn.execute("UPDATE project_contexts SET is_active = 0")
            conn.commit()
        logger.info("Deactivated all active project contexts.")

    def get_context_item(self) -> Optional[ContextItem]:
        """Convert active project into a candidate ContextItem if present."""
        proj = self.get_active_project()
        if not proj:
            return None

        content = proj.to_context_block()
        return ContextItem(
            source=ContextSource.PROJECT_CONTEXT,
            category="workspace",
            content=content,
            relevance_score=0.50,
            priority=7,
            trust_level=TrustLevel.USER,
            is_mandatory=False,
            metadata={"project_id": proj.id, "project_name": proj.project_name},
        )
