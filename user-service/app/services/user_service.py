import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.user import UserProfile

logger = logging.getLogger(__name__)


class UserProfileService:

    @staticmethod
    async def create_profile_from_event(
        db: AsyncSession,
        user_id: str,
        email: str,
        username: str,
    ) -> bool:
        """
        Creates a profile row for a newly registered user.

        Returns True if a new profile was created, False if one
        already existed for this user_id (duplicate event — this is
        the idempotency check: at-least-once delivery means this
        function must be safe to call more than once for the same
        user without creating duplicate rows).
        """
        profile = UserProfile(
            user_id=user_id,
            email=email,
            username=username,
        )

        db.add(profile)
        try:
            await db.commit()
            return True
        except IntegrityError:
            # user_id UNIQUE constraint violated — this user already
            # has a profile, almost certainly because RabbitMQ
            # redelivered the same event. Roll back the failed insert
            # and treat this as a successful no-op, not an error.
            await db.rollback()
            logger.info(f"Profile already exists for user_id={user_id}, skipping (idempotent)")
            return False