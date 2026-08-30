"""InvokeAI backend (tested against InvokeAI 6.14).

InvokeAI 6.x generates via a node graph enqueued on a queue, then polled. Rather
than reconstruct a graph by hand (fragile, and it differs per model base: SDXL vs
krea-2 vs anima ...), we *capture* the graph from the user's most recent completed
generation and re-submit it with only the prompt / seed / size swapped. That means
whatever the user last set up in the InvokeAI UI (model, LoRAs, VAE, steps) is
reused exactly, for any base type.
"""
import copy
import random
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

import requests

from .base import BackendStatus, GenResult, ImageGenBackend

TEMP_DIR = Path("temp_images")


class InvokeAIBackend(ImageGenBackend):
    id = "invokeai"
    display_name = "InvokeAI"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.base_url = (self.config.get("base_url") or "http://localhost:9090").rstrip("/")
        self.queue_id = self.config.get("queue_id", "default")
        self._template = None
        self._nodes = {}
        self._base_type = None
        self._setup_desc = ""
        self.build_config = None      # set by the app for build-from-scratch mode
        self.img2img_config = None    # {init_path, strength} to lock composition to a reference
        self._last_unresolved = []
        self._init_uploads = {}

    # InvokeAI image-to-latents node type per model base (for img2img).
    I2L_BY_BASE = {
        "sdxl": "i2l", "sdxl-refiner": "i2l", "sd-1": "i2l", "sd-2": "i2l",
        "krea-2": "qwen_image_i2l", "qwen-image": "qwen_image_i2l",
        "anima": "anima_i2l", "z-image": "z_image_i2l",
    }

    def set_build_config(self, cfg):
        """cfg = {model_ref, loras:[{name,weight,ref}], width, height, steps, cfg} or None."""
        self.build_config = cfg

    def set_img2img(self, cfg):
        """cfg = {init_path, strength} — use an image as the composition reference, or None."""
        self.img2img_config = cfg

    def _upload_init(self, path):
        """Upload an init image to InvokeAI once; cache the returned image_name."""
        key = str(path)
        if key in self._init_uploads:
            return self._init_uploads[key]
        with open(path, "rb") as f:
            r = requests.post(
                f"{self.base_url}/api/v1/images/upload",
                params={"image_category": "user", "is_intermediate": "false"},
                files={"file": (Path(path).name, f, "image/png")}, timeout=30,
            )
        r.raise_for_status()
        name = r.json()["image_name"]
        self._init_uploads[key] = name
        return name

    def _apply_img2img(self, graph, base, strength, init_path):
        """Rewrite a txt2img graph into img2img: encode init image → denoise.latents,
        and set denoising_start so `strength` controls how much is restyled."""
        i2l_type = self.I2L_BY_BASE.get(base)
        if not i2l_type:
            raise RuntimeError(f"img2img isn't supported for base '{base}' yet.")
        nodes, edges = graph["nodes"], graph["edges"]
        den = next((nid for nid, n in nodes.items() if "denoise" in (n.get("type") or "")), None)
        if not den:
            raise RuntimeError("No denoise node found for img2img.")
        vae_src = next(((e["source"]["node_id"], e["source"]["field"])
                        for e in edges if e["destination"]["field"] == "vae"), None)
        if not vae_src:
            raise RuntimeError("No VAE source found in graph for img2img.")
        image_name = self._upload_init(init_path)
        i2l = "i2l_" + uuid.uuid4().hex[:8]
        nodes[i2l] = {"id": i2l, "type": i2l_type, "is_intermediate": True,
                      "use_cache": True, "image": {"image_name": image_name}}
        edges.append({"source": {"node_id": vae_src[0], "field": vae_src[1]},
                      "destination": {"node_id": i2l, "field": "vae"}})
        edges.append({"source": {"node_id": i2l, "field": "latents"},
                      "destination": {"node_id": den, "field": "latents"}})
        nodes[den]["denoising_start"] = round(max(0.0, min(1.0, 1.0 - float(strength))), 3)

    # --- reachability -----------------------------------------------------
    def status(self) -> BackendStatus:
        try:
            r = requests.get(f"{self.base_url}/api/v1/app/version", timeout=4)
            if r.ok:
                return BackendStatus(True, f"InvokeAI {r.json().get('version', '?')}")
            return BackendStatus(False, f"HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001 - status must never raise
            return BackendStatus(False, str(e))

    # --- template capture -------------------------------------------------
    @staticmethod
    def _find_node(graph, prefix):
        for nid in graph["nodes"]:
            if nid.split(":")[0] == prefix:
                return nid
        return None

    def capture_template(self):
        """Grab the most recent completed generation graph as the template."""
        r = requests.get(f"{self.base_url}/api/v1/queue/{self.queue_id}/list_all", timeout=15)
        r.raise_for_status()
        items = r.json()
        items = items if isinstance(items, list) else items.get("items", [])
        comp = [
            it for it in items
            if it.get("status") == "completed" and it.get("session", {}).get("graph")
        ]
        if not comp:
            raise RuntimeError(
                "No completed InvokeAI generation to use as a template. "
                "Generate one image in InvokeAI first, then capture again."
            )
        item = comp[-1]
        graph = copy.deepcopy(item["session"]["graph"])
        pid = self._find_node(graph, "positive_prompt")
        sid = self._find_node(graph, "seed")
        if not pid or not sid:
            raise RuntimeError("Could not locate prompt/seed nodes in the captured InvokeAI graph.")

        self._template = graph
        self._nodes = {
            "positive": pid,
            "negative": self._find_node(graph, "negative_prompt"),
            "seed": sid,
            "denoise": self._find_node(graph, "denoise_latents"),
            "metadata": self._find_node(graph, "core_metadata"),
            "output": self._find_node(graph, "canvas_output") or self._find_node(graph, "l2i"),
        }

        # detect base type + describe the setup
        model_name, base = None, None
        for n in graph["nodes"].values():
            m = n.get("model")
            if isinstance(m, dict) and m.get("type") == "main":
                model_name, base = m.get("name"), m.get("base")
                break
        self._base_type = base
        den = graph["nodes"].get(self._nodes["denoise"], {})
        self._setup_desc = (
            f"{model_name or '?'} ({base or '?'}) · "
            f"{den.get('width', '?')}×{den.get('height', '?')} · "
            f"{den.get('steps', '?')} steps · cfg {den.get('cfg_scale', '?')}"
        )
        return self._setup_desc

    def prepare(self):
        if self._template is None:
            self.capture_template()

    def describe_setup(self):
        return self._setup_desc

    def current_seed(self):
        """Seed value baked into the captured graph (InvokeAI's last seed field)."""
        if self._template and self._nodes.get("seed"):
            try:
                return int(self._template["nodes"][self._nodes["seed"]].get("value", 0))
            except (TypeError, ValueError):
                return None
        return None

    def active_loras(self):
        """Active LoRAs — the chosen build set in build mode, else those baked into
        the captured graph. Shape: [{name, hash, key, weight}]."""
        if self.build_config:
            out = []
            for l in self.build_config.get("loras", []):
                ref = l.get("ref") or {}
                out.append({"name": l.get("name") or ref.get("name"), "hash": ref.get("hash"),
                            "key": ref.get("key"), "weight": l.get("weight"),
                            "inject": bool(l.get("inject"))})
            return out
        if not self._template:
            return []
        out = []
        for nid, n in self._template["nodes"].items():
            if n.get("type", "").endswith("lora_selector") or n.get("type") == "lora_selector":
                lora = n.get("lora") or {}
                out.append({
                    "name": lora.get("name"), "hash": lora.get("hash"),
                    "key": lora.get("key"), "weight": n.get("weight"), "node_id": nid,
                })
        return out

    # --- generation -------------------------------------------------------
    def _build_capture_graph(self, prompt, negative, params):
        """Capture engine: clone the captured graph and substitute prompt/seed/size."""
        if self._template is None:
            self.capture_template()
        graph = copy.deepcopy(self._template)
        nodes = graph["nodes"]

        seed = params.get("seed")
        if seed is None:
            seed = random.randint(0, 2**31 - 1)
        seed = int(seed)

        nodes[self._nodes["positive"]]["value"] = prompt
        if self._nodes["negative"] and negative:
            nodes[self._nodes["negative"]]["value"] = negative
        nodes[self._nodes["seed"]]["value"] = seed

        # krea-2 is a turbo model: steps MUST be 8 and cfg MUST be 1 or output degrades.
        overrides = dict(params)
        if self._base_type == "krea-2":
            overrides["steps"] = 8
            overrides["cfg_scale"] = 1

        for target in (self._nodes["denoise"], self._nodes["metadata"]):
            if not target:
                continue
            node = nodes[target]
            for k in ("width", "height", "steps", "cfg_scale"):
                if overrides.get(k) is not None and k in node:
                    node[k] = overrides[k]
            if target == self._nodes["denoise"] and "seed" in node:
                node["seed"] = seed
        return graph, seed

    def enqueue_and_wait(self, graph, seed, timeout=300, progress=None, output_node=None):
        """Enqueue a ready graph, poll to completion, download the image → GenResult."""
        if progress:
            progress("Enqueuing generation…")
        payload = {"prepend": False, "batch": {"graph": graph, "runs": 1}}
        r = requests.post(
            f"{self.base_url}/api/v1/queue/{self.queue_id}/enqueue_batch", json=payload, timeout=30
        )
        if not r.ok:
            raise RuntimeError(f"InvokeAI enqueue failed: HTTP {r.status_code} {r.text[:300]}")
        item_ids = r.json().get("item_ids", [])
        if not item_ids:
            raise RuntimeError("InvokeAI accepted the batch but returned no queue item.")
        item_id = item_ids[0]

        t0 = time.time()
        img_name = None
        while time.time() - t0 < timeout:
            ri = requests.get(
                f"{self.base_url}/api/v1/queue/{self.queue_id}/i/{item_id}", timeout=10
            ).json()
            st = ri.get("status")
            if progress and st == "in_progress":
                progress("Generating…")
            if st == "completed":
                results = ri.get("session", {}).get("results", {})
                out = (results.get(output_node) if output_node else None) \
                    or (results.get(self._nodes.get("output")) if self._nodes.get("output") else None) \
                    or next((v for v in results.values() if isinstance(v, dict) and "image" in v), None)
                if out and "image" in out:
                    img_name = out["image"]["image_name"]
                break
            if st in ("failed", "canceled"):
                raise RuntimeError(f"InvokeAI generation {st}: {ri.get('error_message') or ''}")
            time.sleep(1.5)

        if not img_name:
            raise RuntimeError("InvokeAI generation timed out or produced no image.")

        if progress:
            progress("Downloading result…")
        img = requests.get(f"{self.base_url}/api/v1/images/i/{img_name}/full", timeout=60)
        img.raise_for_status()
        TEMP_DIR.mkdir(exist_ok=True)
        out_path = TEMP_DIR / f"invoke_{uuid.uuid4().hex[:8]}_{img_name}"
        out_path.write_bytes(img.content)
        return GenResult(image_path=out_path, seed=seed,
                         meta={"image_name": img_name, "backend": self.id})

    def generate(self, prompt, negative="", params=None, progress=None):
        params = params or {}
        if self.build_config:
            import ipush_bridge
            bc = self.build_config
            if progress:
                progress("Building graph from scratch…")
            graph, seed, unresolved = ipush_bridge.build_graph_for(
                model_ref=bc.get("model_ref"), prompt=prompt, negative=negative,
                seed=params.get("seed"), width=bc.get("width", 1024), height=bc.get("height", 1024),
                steps=bc.get("steps", 30), cfg=bc.get("cfg", 7.0),
                loras=[(l["name"], l["weight"], l.get("ref")) for l in bc.get("loras", [])],
            )
            self._last_unresolved = unresolved
            base = (bc.get("model_ref") or {}).get("base")
        else:
            graph, seed = self._build_capture_graph(prompt, negative, params)
            base = self._base_type
        if self.img2img_config and self.img2img_config.get("init_path"):
            if progress:
                progress("Applying img2img reference…")
            self._apply_img2img(graph, base, self.img2img_config.get("strength", 0.6),
                                self.img2img_config["init_path"])
        return self.enqueue_and_wait(graph, seed, params.get("timeout", 300), progress)
