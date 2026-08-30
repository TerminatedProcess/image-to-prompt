"""ComfyUI backend — skeleton.

Proves the abstraction seam: same capture-and-substitute pattern as InvokeAI, but
against ComfyUI's `/prompt` API. Left as a stub because ComfyUI was not running
when this was built. To finish it: save a ComfyUI workflow (API format) as the
template, substitute the positive-prompt / seed / size nodes, POST to `/prompt`,
poll `/history/{prompt_id}`, then download from `/view`.
"""
from typing import Optional

import requests

from .base import BackendStatus, GenResult, ImageGenBackend


class ComfyUIBackend(ImageGenBackend):
    id = "comfyui"
    display_name = "ComfyUI"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.base_url = (self.config.get("base_url") or "http://localhost:8188").rstrip("/")

    def status(self) -> BackendStatus:
        try:
            r = requests.get(f"{self.base_url}/system_stats", timeout=4)
            return BackendStatus(r.ok, "ComfyUI reachable" if r.ok else f"HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            return BackendStatus(False, str(e))

    def generate(self, prompt, negative="", params=None, progress=None) -> GenResult:
        raise NotImplementedError(
            "ComfyUI backend is a stub. Implement submit/poll against /prompt using a "
            "saved workflow template (same pattern as InvokeAIBackend)."
        )
