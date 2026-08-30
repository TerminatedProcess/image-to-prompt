"""Bridge to the local `invokepush` project for building InvokeAI generation
graphs from scratch (any base: SDXL / krea-2 / anima / …) with a chosen model +
LoRAs, instead of reusing a captured graph.

Defensive: if invokepush or InvokeAI-Meta isn't present, `available()` is False
and the app falls back to the capture engine. All coupling lives here.
"""
import random
import sys

IPUSH_DIR = "/home/dev/work/media/invokedev/invokepush"
_MAX_SEED = 2**32 - 1

_ip = None
_loaded = False


def _load():
    global _ip, _loaded
    if _loaded:
        return _ip
    _loaded = True
    try:
        if IPUSH_DIR not in sys.path:
            sys.path.insert(0, IPUSH_DIR)
        import invokepush as ip  # noqa: E402
        _ip = ip
    except Exception:
        _ip = None
    return _ip


def available():
    return _load() is not None


def current_model_ref():
    """The model currently selected in InvokeAI's UI (live from client_state)."""
    ip = _load()
    if not ip:
        return None
    try:
        mm = ip.get_current_invokeai_model()
        return mm.model_ref if mm else None
    except Exception:
        return None


def match_lora_ref(name, threshold=0.5):
    """Resolve a LoRA name to an InvokeAI model ref (dict), or None if not usable."""
    ip = _load()
    if not ip:
        return None
    try:
        m = ip.match_model(name, "lora", threshold)
        if m and m.source == "invokeai" and m.model_ref:
            return m.model_ref
    except Exception:
        pass
    return None


def build_graph_for(model_ref, prompt, negative="", seed=None,
                    width=1024, height=1024, steps=30, cfg=7.0, loras=None):
    """Build + return an InvokeAI graph. `loras` = list of (name, weight, ref?).

    Returns (graph, used_seed, unresolved_names). Raises RuntimeError on failure.
    """
    ip = _load()
    if not ip:
        raise RuntimeError("invokepush is not available on this machine.")
    if not model_ref:
        raise RuntimeError("No InvokeAI model selected.")

    used_seed = int(seed) if seed is not None else random.randint(0, _MAX_SEED)
    base = model_ref.get("base")

    model_match = ip.ModelMatch(
        query="", matched_name=model_ref.get("name"), matched_key=model_ref.get("key"),
        match_score=1.0, source="invokeai", model_ref=model_ref,
    )

    lora_matches, unresolved = [], []
    for entry in (loras or []):
        name, weight = entry[0], entry[1]
        ref = entry[2] if len(entry) > 2 and entry[2] else match_lora_ref(name)
        if ref and ref.get("base") == base:
            lm = ip.ModelMatch(query=name, matched_name=ref.get("name"), matched_key=ref.get("key"),
                               match_score=1.0, source="invokeai", model_ref=ref)
            lora_matches.append((ip.LoRARef(name, float(weight)), lm))
        else:
            unresolved.append(name)

    meta = ip.ParsedMetadata(
        prompt=prompt, negative_prompt=negative or "", seed=used_seed,
        width=int(width), height=int(height), steps=int(steps), cfg_scale=float(cfg),
    )
    graph = ip.build_graph(meta, model_match, lora_matches)
    if not graph:
        raise RuntimeError(
            f"build_graph returned nothing for base '{base}' — missing submodels "
            "(VAE/encoder) or unsupported base."
        )
    return graph, used_seed, unresolved
