"""Abstract image-generation backend.

A backend takes a text prompt and returns a generated image on disk. Concrete
backends (InvokeAI, ComfyUI, hosted APIs, ...) subclass this so the refine loop
can drive any of them through the same interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class GenResult:
    image_path: Path
    seed: int
    meta: dict = field(default_factory=dict)


@dataclass
class BackendStatus:
    available: bool
    detail: str = ""


class ImageGenBackend(ABC):
    id: str = "base"
    display_name: str = "Base"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def status(self) -> BackendStatus:
        """Cheap reachability check. Never raises."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        negative: str = "",
        params: Optional[dict] = None,
        progress: Optional[Callable[[str], None]] = None,
    ) -> GenResult:
        """Blocking: generate ONE image from `prompt` and return it downloaded to
        disk. Raise RuntimeError with a human-readable message on any failure."""

    def prepare(self) -> None:
        """Optional one-time setup (e.g. capture a template). Raise on failure."""

    def describe_setup(self) -> str:
        """Human-readable summary of the current generation setup, if any."""
        return ""
