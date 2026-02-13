"""
SMC (Structured Memory Core) Integration Service
Implements the 5-layer security architecture:
1. PI Guard - Adversarial pattern detection
2. Sanitizer - Content cleaning
3. Resolver - Integrity verification (SHA-256)
4. Tool Whitelist - Execution control
5. CIFS Audit - Comprehensive logging
"""

import hashlib
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from loguru import logger

from app.core.config import settings
from app.core.database import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession


class SMCService:
    """Structured Memory Core integration service"""
    
    # ============================================
    # Layer 1: PI GUARD - Adversarial Detection
    # ============================================
    
    # Adversarial patterns to detect
    ADVERSARIAL_PATTERNS = [
        r"ignore\s+(previous|all|prior)\s+instructions?",
        r"disregard\s+(previous|all|prior)\s+(instructions?|prompts?)",
        r"forget\s+(everything|all|previous)",
        r"reveal\s+(system\s+)?prompts?",
        r"show\s+(system\s+)?prompts?",
        r"you\s+are\s+now",
        r"new\s+instructions?",
        r"override\s+instructions?",
        r"bypass\s+(security|restrictions?|filters?)",
        r"jailbreak",
        r"pretend\s+you\s+are",
        r"roleplay\s+as",
        r"\[SYSTEM\]",
        r"\[ADMIN\]",
        r"<system>",
        r"</system>",
    ]
    
    @classmethod
    async def pi_guard_check(cls, content: str, user_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Layer 1: Check for adversarial patterns
        Returns: {
            "passed": bool,
            "flagged_patterns": List[str],
            "risk_score": float
        }
        """
        if not settings.SMC_PI_GUARD_ENABLED:
            return {"passed": True, "flagged_patterns": [], "risk_score": 0.0}
        
        flagged = []
        content_lower = content.lower()
        
        for pattern in cls.ADVERSARIAL_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                flagged.append(pattern)
        
        risk_score = len(flagged) / len(cls.ADVERSARIAL_PATTERNS)
        passed = risk_score < 0.1  # Threshold: 10%
        
        if not passed:
            logger.warning(f"PI Guard flagged content from user {user_id}: {flagged}")
            await cls._log_security_event(
                user_id=user_id,
                layer="PI_GUARD",
                action="adversarial_pattern_detected",
                details={"patterns": flagged, "risk_score": risk_score}
            )
        
        return {
            "passed": passed,
            "flagged_patterns": flagged,
            "risk_score": risk_score
        }
    
    # ============================================
    # Layer 2: SANITIZER - Content Cleaning
    # ============================================
    
    @classmethod
    async def sanitize_content(cls, content: str, content_type: str = "text") -> str:
        """
        Layer 2: Clean and sanitize content
        Removes HTML scripts, event handlers, and PII patterns
        """
        if not settings.SMC_SANITIZER_ENABLED:
            return content
        
        sanitized = content
        
        # Remove HTML script tags
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove event handlers
        sanitized = re.sub(r'\son\w+\s*=\s*["\'][^"\']*["\']', '', sanitized, flags=re.IGNORECASE)
        
        # Remove inline JavaScript
        sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)
        
        # Remove potentially dangerous tags (if HTML)
        if content_type == "html":
            dangerous_tags = ['iframe', 'embed', 'object', 'applet']
            for tag in dangerous_tags:
                sanitized = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)
        
        # Basic PII redaction (optional - can be made more sophisticated)
        # SSN pattern (XXX-XX-XXXX)
        sanitized = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]', sanitized)
        
        # Credit card pattern (basic)
        sanitized = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CC_REDACTED]', sanitized)
        
        return sanitized
    
    # ============================================
    # Layer 3: RESOLVER - Integrity Verification
    # ============================================
    
    @classmethod
    def compute_hash(cls, content: str) -> str:
        """Compute SHA-256 hash for content integrity"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    @classmethod
    async def verify_integrity(cls, content: str, expected_hash: str) -> bool:
        """
        Layer 3: Verify content integrity against canonical hash
        Returns True if hash matches, False otherwise
        """
        if not settings.SMC_RESOLVER_ENABLED:
            return True
        
        actual_hash = cls.compute_hash(content)
        
        if actual_hash != expected_hash:
            logger.error(f"Integrity violation: expected {expected_hash}, got {actual_hash}")
            await cls._log_security_event(
                layer="RESOLVER",
                action="integrity_violation",
                details={
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash
                }
            )
            return False
        
        return True
    
    @classmethod
    async def store_canonical(
        cls,
        content: str,
        content_type: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Store content in canonical store with hash
        Returns: {
            "content_hash": str,
            "version": int,
            "stored_at": datetime
        }
        """
        content_hash = cls.compute_hash(content)
        
        async with get_db_session() as session:
            # Check if already exists
            from app.models.smc import CanonicalStore
            
            existing = await session.execute(
                f"SELECT * FROM canonical_store WHERE content_hash = '{content_hash}'"
            )
            
            if existing.first():
                logger.debug(f"Content already in canonical store: {content_hash}")
                return {
                    "content_hash": content_hash,
                    "version": 1,
                    "stored_at": datetime.utcnow(),
                    "duplicate": True
                }
            
            # Insert new canonical entry
            await session.execute(
                """
                INSERT INTO canonical_store (content_type, content, content_hash, metadata)
                VALUES (:type, :content, :hash, :metadata)
                """,
                {
                    "type": content_type,
                    "content": content,
                    "hash": content_hash,
                    "metadata": metadata or {}
                }
            )
            await session.commit()
        
        return {
            "content_hash": content_hash,
            "version": 1,
            "stored_at": datetime.utcnow(),
            "duplicate": False
        }
    
    # ============================================
    # Layer 4: TOOL WHITELIST - Access Control
    # ============================================
    
    ALLOWED_TOOLS = {
        "read": ["query_documents", "search_memory", "get_conversation"],
        "write": ["store_document", "create_conversation", "add_message"],
        "admin": ["delete_document", "purge_memory", "export_data"]
    }
    
    @classmethod
    async def check_tool_permission(
        cls,
        tool_name: str,
        user_role: str,
        admin_token: Optional[str] = None
    ) -> bool:
        """
        Layer 4: Check if user has permission to use tool
        """
        if not settings.SMC_TOOL_WHITELIST_ENABLED:
            return True
        
        # Admin tools require admin token
        if tool_name in cls.ALLOWED_TOOLS.get("admin", []):
            if admin_token != settings.SMC_ADMIN_TOKEN:
                logger.warning(f"Unauthorized admin tool access attempt: {tool_name}")
                await cls._log_security_event(
                    layer="TOOL_WHITELIST",
                    action="unauthorized_admin_tool",
                    details={"tool": tool_name}
                )
                return False
            return True
        
        # Write tools require user or admin role
        if tool_name in cls.ALLOWED_TOOLS.get("write", []):
            if user_role not in ["user", "admin"]:
                logger.warning(f"Unauthorized write tool access: {tool_name} by {user_role}")
                return False
            return True
        
        # Read tools are allowed for all authenticated users
        if tool_name in cls.ALLOWED_TOOLS.get("read", []):
            return True
        
        # Unknown tool - deny
        logger.warning(f"Unknown tool requested: {tool_name}")
        return False
    
    # ============================================
    # Layer 5: CIFS AUDIT - Comprehensive Logging
    # ============================================
    
    @classmethod
    async def audit_log(
        cls,
        user_id: Optional[UUID],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        request_body: Optional[Dict] = None,
        response_status: Optional[int] = None,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UUID:
        """
        Layer 5: Log all interactions to audit trail
        Returns audit log ID
        """
        if not settings.SMC_CIFS_AUDIT_ENABLED:
            return uuid4()
        
        async with get_db_session() as session:
            request_id = uuid4()
            
            await session.execute(
                """
                INSERT INTO audit_log (
                    request_id, user_id, action, resource_type, resource_id,
                    ip_address, user_agent, request_body, response_status, error_message,
                    security_layer, created_at
                )
                VALUES (
                    :request_id, :user_id, :action, :resource_type, :resource_id,
                    :ip_address, :user_agent, :request_body, :response_status, :error_message,
                    'AUDIT', :created_at
                )
                """,
                {
                    "request_id": request_id,
                    "user_id": user_id,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "request_body": request_body,
                    "response_status": response_status,
                    "error_message": error_message,
                    "created_at": datetime.utcnow()
                }
            )
            await session.commit()
        
        return request_id
    
    @classmethod
    async def _log_security_event(
        cls,
        layer: str,
        action: str,
        details: Dict[str, Any],
        user_id: Optional[UUID] = None
    ):
        """Internal helper to log security events"""
        async with get_db_session() as session:
            await session.execute(
                """
                INSERT INTO audit_log (
                    request_id, user_id, action, security_layer, 
                    flagged, flag_reason, request_body, created_at
                )
                VALUES (
                    :request_id, :user_id, :action, :layer,
                    true, :reason, :details, :created_at
                )
                """,
                {
                    "request_id": uuid4(),
                    "user_id": user_id,
                    "action": action,
                    "layer": layer,
                    "reason": f"{layer} security check failed",
                    "details": details,
                    "created_at": datetime.utcnow()
                }
            )
            await session.commit()


# Create singleton instance
smc_service = SMCService()
