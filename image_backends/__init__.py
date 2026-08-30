"""Pluggable image-generation backends for the auto-refine loop.

Add a new backend by subclassing ImageGenBackend and registering it below.
"""
from .base import BackendStatus, GenResult, ImageGenBackend
from .comfyui import ComfyUIBackend
from .invokeai import InvokeAIBackend

_BACKENDS = {cls.id: cls for cls in (InvokeAIBackend, ComfyUIBackend)}


def list_backend_ids():
    return list(_BACKENDS.keys())


def backend_display_names():
    return {bid: cls.display_name for bid, cls in _BACKENDS.items()}


def get_backend(backend_id, config=None) -> ImageGenBackend:
    cls = _BACKENDS.get(backend_id)
    if not cls:
        raise ValueError(f"Unknown image backend: {backend_id}")
    return cls(config)


__all__ = [
    "ImageGenBackend",
    "GenResult",
    "BackendStatus",
    "list_backend_ids",
    "backend_display_names",
    "get_backend",
]
