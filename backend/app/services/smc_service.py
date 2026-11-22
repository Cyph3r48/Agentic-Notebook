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
import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from datetime import timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from loguru import logger

from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AuditEvent, CanonicalStore


class SMCService:
    """Structured Memory Core integration service"""
    
    # ============================================
    # Layer 1: PI GUARD - Adversarial Detection
    # ============================================
    
    # Explicit injection attempts: one match flags the text.
    STRONG_PATTERNS = {
        "ignore_instructions": r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier|all)\s+(?:instructions?|prompts?|rules?)",
        "disregard_instructions": r"disregard\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier|all)\s+(?:instructions?|prompts?|rules?)",
        "forget_everything": r"forget\s+(?:everything|all\s+(?:previous|prior)|your\s+instructions)",
        "reveal_system_prompt": r"(?:reveal|print|repeat|output|leak)\s+(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instructions)",
        "override_instructions": r"override\s+(?:your\s+|the\s+|all\s+)?(?:instructions?|rules|safety)",
        "bypass_security": r"bypass\s+(?:the\s+)?(?:security|restrictions?|filters?|safety|guardrails?)",
        "jailbreak": r"jailbreak",
        "system_tag": r"(?:\[system\]|\[admin\]|</?system>)",
    }
    # Phrases that are also ordinary English ("new instructions for the desk"): two different ones flag the text.
    WEAK_PATTERNS = {
        "you_are_now": r"you\s+are\s+now\b",
        "new_instructions": r"new\s+instructions?",
        "pretend": r"pretend\s+(?:you\s+are|to\s+be)",
        "roleplay": r"role-?play\s+as",
        "show_prompt": r"show\s+(?:me\s+)?(?:your\s+|the\s+)?(?:system\s+)?prompts?",
    }
    WEAK_MATCHES_TO_FLAG = 2

    _INVISIBLE = re.compile("[\u200b-\u200f\u2060\ufeff\u00ad]")

    @dataclass
    class PIScan:
        flagged: bool
        strong: list[str] = field(default_factory=list)
        weak: list[str] = field(default_factory=list)
        risk_score: float = 0.0

        @property
        def patterns(self) -> list[str]:
            return [*self.strong, *self.weak]

    @classmethod
    def _normalize_for_scan(cls, content: str) -> str:
        """Fold look-alike characters and drop invisible ones so "i\u200bgnore" and full-width text still match."""
        text = unicodedata.normalize("NFKC", content)
        text = cls._INVISIBLE.sub("", text)
        return re.sub(r"\s+", " ", text).lower()

    @classmethod
    def scan_text(cls, content: str) -> "SMCService.PIScan":
        """Layer 1 as a pure function: no I/O, so it can run on every retrieved chunk."""
        if not settings.SMC_PI_GUARD_ENABLED or not content:
            return cls.PIScan(flagged=False)
        text = cls._normalize_for_scan(content)
        strong = [name for name, pattern in cls.STRONG_PATTERNS.items() if re.search(pattern, text)]
        weak = [name for name, pattern in cls.WEAK_PATTERNS.items() if re.search(pattern, text)]
        flagged = bool(strong) or len(weak) >= cls.WEAK_MATCHES_TO_FLAG
        score = min(1.0, len(strong) * 1.0 + len(weak) * 0.4)
        return cls.PIScan(flagged=flagged, strong=strong, weak=weak, risk_score=score)

    @classmethod
    async def pi_guard_check(cls, content: str, user_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Layer 1: Check for adversarial patterns
        Returns: {"passed": bool, "flagged_patterns": List[str] (names, not regexes), "risk_score": float}
        """
        scan = cls.scan_text(content)
        if scan.flagged:
            logger.warning("PI Guard flagged content user_id={user_id} patterns={patterns}", user_id=user_id, patterns=scan.patterns)
            await cls._log_security_event(
                user_id=user_id,
                layer="PI_GUARD",
                action="adversarial_pattern_detected",
                details={"patterns": scan.patterns, "risk_score": scan.risk_score},
            )
        return {"passed": not scan.flagged, "flagged_patterns": scan.patterns, "risk_score": scan.risk_score}

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
    def hash_matches(cls, content: str, expected_hash: str | None) -> bool:
        """Layer 3 as a pure check. A chunk with no stored hash cannot be verified and is treated as failing."""
        if not settings.SMC_RESOLVER_ENABLED:
            return True
        return bool(expected_hash) and cls.compute_hash(content) == expected_hash

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
        
        async with SessionLocal() as session:
            existing = await session.scalar(
                select(CanonicalStore).where(CanonicalStore.content_hash == content_hash)
            )

            if existing is not None:
                logger.debug(f"Content already in canonical store: {content_hash}")
                return {
                    "content_hash": content_hash,
                    "version": 1,
                    "stored_at": datetime.now(tz=timezone.utc),
                    "duplicate": True
                }
            
            session.add(
                CanonicalStore(
                    content_type=content_type,
                    content=content,
                    content_hash=content_hash,
                    metadata_json=metadata or {},
                )
            )
            await session.commit()
        
        return {
            "content_hash": content_hash,
            "version": 1,
            "stored_at": datetime.now(tz=timezone.utc),
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
    
    @staticmethod
    def _valid_ip(value: Optional[str]) -> Optional[str]:
        """The audit table stores a real IP address; anything else (a test client, a proxy name) becomes NULL."""
        try:
            return str(ipaddress.ip_address(value)) if value else None
        except ValueError:
            return None

    @classmethod
    async def _write_audit(cls, event: Dict[str, Any]) -> None:
        """Persist one audit row in its own session, so a failed request is still recorded.

        Never raises: a broken audit trail is logged at error level but must not take the app down.
        """
        try:
            async with SessionLocal() as session:
                session.add(AuditEvent(**event))
                await session.commit()
        except Exception as exc:
            logger.error("Audit write failed action={action}: {error}", action=event.get("action"), error=type(exc).__name__)

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
        user_agent: Optional[str] = None,
        request_id: Optional[UUID] = None,
        flagged: bool = False,
        flag_reason: Optional[str] = None,
        security_layer: str = "AUDIT",
    ) -> UUID:
        """
        Layer 5: Log an interaction to the audit trail. `request_body` must hold metadata only (sizes, ids, flags),
        never message text, document text, passwords or keys. Returns the audit request id.
        """
        audit_request_id = request_id or uuid4()
        if not settings.SMC_CIFS_AUDIT_ENABLED:
            return audit_request_id
        await cls._write_audit(
            {
                "request_id": audit_request_id,
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "ip_address": cls._valid_ip(ip_address),
                "user_agent": (user_agent or "")[:500] or None,
                "request_body": request_body,
                "response_status": response_status,
                "error_message": error_message,
                "security_layer": security_layer,
                "flagged": flagged,
                "flag_reason": flag_reason,
            }
        )
        return audit_request_id

    @classmethod
    async def _log_security_event(
        cls,
        layer: str,
        action: str,
        details: Dict[str, Any],
        user_id: Optional[UUID] = None,
        request_id: Optional[UUID] = None,
    ) -> None:
        """A flagged event: something a security layer refused or caught."""
        if not settings.SMC_CIFS_AUDIT_ENABLED:
            return
        await cls._write_audit(
            {
                "request_id": request_id or uuid4(),
                "user_id": user_id,
                "action": action,
                "security_layer": layer,
                "flagged": True,
                "flag_reason": f"{layer} security check failed",
                "request_body": details,
            }
        )


# Create singleton instance
smc_service = SMCService()
