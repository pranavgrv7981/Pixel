"""User profile and personalization management."""

from typing import Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.context.database import ContextDatabase
from app.context.models import (
    ContextItem,
    ContextSource,
    ResponseStyle,
    TrustLevel,
    UserProfile,
)

logger = get_logger("context.profile")


class UserProfileManager:
    """Manages persistent user preferences, personalization settings, and response styles."""

    def __init__(
        self,
        db: Optional[ContextDatabase] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db or ContextDatabase(settings=self.settings)

    def get_profile(self) -> UserProfile:
        """Fetch active user profile."""
        return self.db.get_user_profile()

    def update_profile(
        self,
        preferred_name: Optional[str] = None,
        response_style: Optional[ResponseStyle] = None,
        preferred_language: Optional[str] = None,
        technical_level: Optional[str] = None,
        timezone: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> UserProfile:
        """Update and persist user profile attributes."""
        current = self.get_profile()
        updated = UserProfile(
            preferred_name=preferred_name if preferred_name is not None else current.preferred_name,
            response_style=response_style if response_style is not None else current.response_style,
            preferred_language=preferred_language if preferred_language is not None else current.preferred_language,
            technical_level=technical_level if technical_level is not None else current.technical_level,
            timezone=timezone if timezone is not None else current.timezone,
            custom_instructions=custom_instructions if custom_instructions is not None else current.custom_instructions,
        )
        saved = self.db.save_user_profile(updated)
        logger.info("Updated user profile: response_style=%s, name=%s", saved.response_style.value, saved.preferred_name)
        return saved

    def get_context_item(self) -> Optional[ContextItem]:
        """Convert current profile into a candidate ContextItem if instructions exist."""
        profile = self.get_profile()
        instruction = profile.to_system_instruction()
        if not instruction:
            return None

        return ContextItem(
            source=ContextSource.USER_PROFILE,
            category="personalization",
            content=f"USER PREFERENCES: {instruction}",
            relevance_score=0.40,
            priority=8,
            trust_level=TrustLevel.USER,
            is_mandatory=False,
            metadata={"response_style": profile.response_style.value},
        )
