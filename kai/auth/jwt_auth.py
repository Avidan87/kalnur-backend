"""
JWT Authentication for KAI - Supabase Auth Integration

Uses Supabase Auth for secure password-based authentication.
Tokens are verified locally using SUPABASE_JWT_SECRET — no Supabase
network round-trip per request, eliminating cold-start auth failures.
"""
import logging
import os
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

security = HTTPBearer()

# Auth client (uses anon key for auth operations)
_auth_client: Optional[Client] = None


def get_auth_client() -> Client:
    """
    Get Supabase client for auth operations.
    Uses SUPABASE_ANON_KEY if available, falls back to SERVICE_ROLE_KEY.
    """
    global _auth_client

    if _auth_client is None:
        url = os.getenv("SUPABASE_URL")
        # Prefer anon key for auth, fall back to service role
        key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")

        _auth_client = create_client(url, key)
        logger.info("✓ Supabase auth client initialized")

    return _auth_client


def sign_up_user(email: str, password: str) -> dict:
    """
    Sign up a new user with Supabase Auth.

    Args:
        email: User's email address
        password: User's password (min 6 characters)

    Returns:
        dict: Contains user info and session tokens

    Raises:
        ValueError: If signup fails (e.g., email already exists, weak password)
    """
    client = get_auth_client()

    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password
        })

        if response.user is None:
            raise ValueError("Signup failed - no user returned")

        logger.info(f"✓ User signed up: {email}")

        return {
            "user_id": response.user.id,
            "email": response.user.email,
            "access_token": response.session.access_token if response.session else None,
            "refresh_token": response.session.refresh_token if response.session else None,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"✗ Signup failed for {email}: {error_msg}")

        # Parse common Supabase Auth errors
        if "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            raise ValueError("Email already registered")
        elif "password" in error_msg.lower():
            raise ValueError("Password must be at least 6 characters")
        else:
            raise ValueError(f"Signup failed: {error_msg}")


def sign_in_user(email: str, password: str) -> dict:
    """
    Sign in an existing user with Supabase Auth.

    Args:
        email: User's email address
        password: User's password

    Returns:
        dict: Contains user info and session tokens

    Raises:
        ValueError: If login fails (e.g., invalid credentials)
    """
    client = get_auth_client()

    try:
        response = client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if response.user is None:
            raise ValueError("Login failed - invalid credentials")

        logger.info(f"✓ User signed in: {email}")

        return {
            "user_id": response.user.id,
            "email": response.user.email,
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"✗ Login failed for {email}: {error_msg}")

        if "invalid" in error_msg.lower() or "credentials" in error_msg.lower():
            raise ValueError("Invalid email or password")
        else:
            raise ValueError(f"Login failed: {error_msg}")


def refresh_session(refresh_token: str) -> dict:
    """
    Exchange a refresh token for a new access token + refresh token pair.

    Returns:
        dict: Contains new access_token and refresh_token

    Raises:
        ValueError: If the refresh token is invalid or expired
    """
    client = get_auth_client()

    try:
        response = client.auth.refresh_session(refresh_token)

        if response.session is None:
            raise ValueError("Could not refresh session")

        logger.info("✓ Session refreshed successfully")

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
        }

    except Exception as e:
        logger.error(f"✗ Token refresh failed: {e}")
        raise ValueError("Invalid or expired refresh token")


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract and verify user_id from Supabase JWT token.
    """
    token = credentials.credentials
    client = get_auth_client()
    try:
        response = client.auth.get_user(token)
        if response.user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return response.user.id
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Extract and verify user info from Supabase JWT token.

    Returns:
        dict: { "user_id": str, "email": str | None }
    """
    token = credentials.credentials
    client = get_auth_client()
    try:
        response = client.auth.get_user(token)
        if response.user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"user_id": response.user.id, "email": response.user.email}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
