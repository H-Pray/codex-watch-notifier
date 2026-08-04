"""Shared notification models and provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import sys


class NotificationStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"


@dataclass(frozen=True)
class Notification:
    title: str
    message: str
    status: NotificationStatus = NotificationStatus.INFO


class NotificationError(RuntimeError):
    """Raised when a provider cannot deliver a notification."""


class NotificationProvider(ABC):
    """Interface implemented by all notification backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @abstractmethod
    def send(self, notification: Notification) -> None:
        """Deliver a notification or raise NotificationError."""


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    delivered: bool
    error: str | None = None


class NotifierService:
    """Fan out a notification while isolating failures between providers."""

    def __init__(self, providers: list[NotificationProvider]) -> None:
        self.providers = providers

    def send(self, notification: Notification, *, dry_run: bool = False) -> list[DeliveryResult]:
        results: list[DeliveryResult] = []
        for provider in self.providers:
            if dry_run:
                line = f"[dry-run] {provider.name}: {notification.title} - {notification.message}"
                # Some Windows terminals still use a legacy encoding such as GBK.
                # Keep emoji in real notifications, but escape unsupported console
                # characters rather than failing after the Codex task has finished.
                encoding = getattr(sys.stdout, "encoding", None)
                if encoding:
                    line = line.encode(encoding, errors="backslashreplace").decode(encoding)
                print(line)
                results.append(DeliveryResult(provider=provider.name, delivered=True))
                continue
            try:
                provider.send(notification)
            except Exception as exc:  # Provider bugs must not block other providers.
                results.append(
                    DeliveryResult(provider=provider.name, delivered=False, error=str(exc))
                )
            else:
                results.append(DeliveryResult(provider=provider.name, delivered=True))
        return results
