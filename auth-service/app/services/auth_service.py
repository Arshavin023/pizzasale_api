# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from app.models.user import UserAuth
# from app.core.security import hash_password, verify_password


# class AuthError(Exception):
#     """Raised for known, user-facing auth failures (not server errors)."""
#     pass


# class AuthService:

#     @staticmethod
#     async def register(db: AsyncSession, data):
#         result = await db.execute(
#             select(UserAuth).where(UserAuth.username == data.username)
#         )
#         if result.scalar_one_or_none():
#             raise AuthError("Username already exists")

#         result = await db.execute(
#             select(UserAuth).where(UserAuth.email == data.email)
#         )
#         if result.scalar_one_or_none():
#             raise AuthError("Email already exists")

#         user = UserAuth(
#             username=data.username,
#             email=data.email,
#             password=hash_password(data.password),
#             is_active=False,
#         )

#         db.add(user)
#         await db.commit()
#         await db.refresh(user)

#         return user

#     @staticmethod
#     async def authenticate(db: AsyncSession, data):
#         result = await db.execute(
#             select(UserAuth).where(UserAuth.username == data.username)
#         )
#         user = result.scalar_one_or_none()

#         if not user or not verify_password(data.password, user.password):
#             return None

#         return user

#     @staticmethod
#     async def activate_user_by_email(db: AsyncSession, email: str) -> bool:
#         """
#         Marks the user with the given email as active.
#         Returns True if a matching user was found and activated,
#         False if no such user exists.
#         """
#         result = await db.execute(
#             select(UserAuth).where(UserAuth.email == email)
#         )
#         user = result.scalar_one_or_none()

#         if not user:
#             return False

#         if not user.is_active:
#             user.is_active = True
#             await db.commit()

#         return True


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import UserAuth
from app.core.security import hash_password, verify_password
from app.utils.events import publish_user_registered


class AuthError(Exception):
    """Raised for known, user-facing auth failures (not server errors)."""
    pass


class AuthService:

    @staticmethod
    async def register(db: AsyncSession, data):
        result = await db.execute(
            select(UserAuth).where(UserAuth.username == data.username)
        )
        if result.scalar_one_or_none():
            raise AuthError("Username already exists")

        result = await db.execute(
            select(UserAuth).where(UserAuth.email == data.email)
        )
        if result.scalar_one_or_none():
            raise AuthError("Email already exists")

        user = UserAuth(
            username=data.username,
            email=data.email,
            password=hash_password(data.password),
            is_active=False,
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        publish_user_registered(
            user_id=user.id,
            email=user.email,
            username=user.username,
        )

        return user

    @staticmethod
    async def authenticate(db: AsyncSession, data):
        result = await db.execute(
            select(UserAuth).where(UserAuth.username == data.username)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.password):
            return None

        return user

    @staticmethod
    async def activate_user_by_email(db: AsyncSession, email: str) -> bool:
        """
        Marks the user with the given email as active.
        Returns True if a matching user was found and activated,
        False if no such user exists.
        """
        result = await db.execute(
            select(UserAuth).where(UserAuth.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        if not user.is_active:
            user.is_active = True
            await db.commit()

        return True
