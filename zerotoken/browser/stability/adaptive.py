"""
Adaptive element locating: fingerprint extraction and similarity-based relocation.
"""

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Default minimum similarity to accept a relocated element (0..1)
RELOCATE_THRESHOLD = 0.45

# Script run in browser to build fingerprint from an element
_FINGERPRINT_SCRIPT = """
(el) => {
  if (!el || !el.tagName) return null;
  const parent = el.parentElement;
  const parentData = parent ? {
    tag: (parent.tagName || '').toLowerCase(),
    attrs: Object.fromEntries([...parent.attributes].map(a => [a.name, a.value])),
    text: (parent.textContent || '').trim().slice(0, 500)
  } : { tag: '', attrs: {}, text: '' };
  const selfData = {
    tag: (el.tagName || '').toLowerCase(),
    attrs: Object.fromEntries([...el.attributes].map(a => [a.name, a.value])),
    text: (el.textContent || '').trim().slice(0, 500),
    siblings: parent ? [...parent.children].filter(c => c !== el).map(c => (c.tagName || '').toLowerCase()) : [],
    path: (() => {
      const p = [];
      let n = el;
      while (n && n !== document.body) {
        p.unshift((n.tagName || '').toLowerCase());
        n = n.parentElement;
      }
      return p;
    })()
  };
  return { parent: parentData, self: selfData };
}
"""


def _attr_similarity(a: dict, b: dict) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    keys_a, keys_b = set(a), set(b)
    if not keys_a and not keys_b:
        return 1.0
    inter = keys_a & keys_b
    same = sum(1 for k in inter if a.get(k) == b.get(k))
    return same / max(len(keys_a | keys_b), 1)


def _text_similarity(t1: str, t2: str) -> float:
    t1, t2 = (t1 or "").strip(), (t2 or "").strip()
    if not t1 and not t2:
        return 1.0
    if not t1 or not t2:
        return 0.0
    if t1 == t2:
        return 1.0
    if t1 in t2 or t2 in t1:
        return 0.8
    # simple overlap
    w1, w2 = set(t1.split()), set(t2.split())
    if not w1 and not w2:
        return 1.0
    return len(w1 & w2) / max(len(w1 | w2), 1) if (w1 or w2) else 0.0


def _list_similarity(path_a: list, path_b: list) -> float:
    if not path_a and not path_b:
        return 1.0
    if not path_a or not path_b:
        return 0.0
    common = 0
    for i, (x, y) in enumerate(zip(path_a, path_b)):
        if x == y:
            common += 1
        else:
            break
    return (2.0 * common) / (len(path_a) + len(path_b)) if (path_a or path_b) else 0.0


def similarity_score(fingerprint_a: Dict[str, Any], fingerprint_b: Dict[str, Any]) -> float:
    """
    Compare two fingerprint dicts and return a similarity score in [0, 1].
    Weights: self.tag, self.attrs, self.text, parent, path, siblings.
    """
    if not fingerprint_a or not fingerprint_b:
        return 0.0
    pa = fingerprint_a.get("parent") or {}
    pb = fingerprint_b.get("parent") or {}
    sa = fingerprint_a.get("self") or {}
    sb = fingerprint_b.get("self") or {}

    tag_s = 1.0 if (sa.get("tag") == sb.get("tag")) else 0.0
    attr_s = _attr_similarity(sa.get("attrs") or {}, sb.get("attrs") or {})
    text_s = _text_similarity(sa.get("text") or "", sb.get("text") or "")
    parent_tag = 1.0 if (pa.get("tag") == pb.get("tag")) else 0.0
    parent_attr = _attr_similarity(pa.get("attrs") or {}, pb.get("attrs") or {})
    path_s = _list_similarity(sa.get("path") or [], sb.get("path") or [])
    sib_a = set(sa.get("siblings") or [])
    sib_b = set(sb.get("siblings") or [])
    sib_s = len(sib_a & sib_b) / max(len(sib_a | sib_b), 1) if (sib_a or sib_b) else 1.0

    w_tag, w_attr, w_text = 0.2, 0.15, 0.2
    w_parent, w_path, w_sib = 0.15, 0.2, 0.1
    score = (
        w_tag * tag_s
        + w_attr * attr_s
        + w_text * text_s
        + w_parent * (0.5 * parent_tag + 0.5 * parent_attr)
        + w_path * path_s
        + w_sib * sib_s
    )
    return round(min(1.0, max(0.0, score)), 4)


async def extract_fingerprint(element_handle: Any, page: Any) -> Optional[Dict[str, Any]]:
    """
    Extract a fingerprint dict from a Playwright ElementHandle.
    Uses in-page JS to read parent/self tag, attrs, text, siblings, path.
    Returns None if evaluation fails or element is invalid.
    """
    try:
        result = await element_handle.evaluate(_FINGERPRINT_SCRIPT)
        return result
    except Exception:
        return None


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc or "default"
    except Exception:
        return "default"


# Script to collect fingerprints for body * elements (first 300) and return list of {i, fp}
_ALL_FINGERPRINTS_SCRIPT = """
() => {
  const fn = (el) => {
    if (!el || !el.tagName) return null;
    const parent = el.parentElement;
    const parentData = parent ? {
      tag: (parent.tagName || '').toLowerCase(),
      attrs: Object.fromEntries([...parent.attributes].map(a => [a.name, a.value])),
      text: (parent.textContent || '').trim().slice(0, 500)
    } : { tag: '', attrs: {}, text: '' };
    const selfData = {
      tag: (el.tagName || '').toLowerCase(),
      attrs: Object.fromEntries([...el.attributes].map(a => [a.name, a.value])),
      text: (el.textContent || '').trim().slice(0, 500),
      siblings: parent ? [...parent.children].filter(c => c !== el).map(c => (c.tagName || '').toLowerCase()) : [],
      path: (() => {
        const p = [];
        let n = el;
        while (n && n !== document.body) {
          p.unshift((n.tagName || '').toLowerCase());
          n = n.parentElement;
        }
        return p;
      })()
    };
    return { parent: parentData, self: selfData };
  };
  const els = document.querySelectorAll('body *');
  const maxN = Math.min(300, els.length);
  const out = [];
  for (let i = 0; i < maxN; i++) {
    const fp = fn(els[i]);
    if (fp) out.push({ i, fp });
  }
  return out;
}
"""


async def relocate(
    page: Any,
    domain: str,
    identifier: str,
    storage: Any,
    threshold: float = RELOCATE_THRESHOLD,
) -> Optional[Any]:
    """
    Find the element on the current page that best matches the stored fingerprint
    for (domain, identifier). Returns the ElementHandle or None if no single best match.
    """
    stored = storage.fingerprint_load(domain, identifier)
    if not stored:
        return None
    try:
        candidates = await page.evaluate(_ALL_FINGERPRINTS_SCRIPT)
    except Exception:
        return None
    if not candidates:
        return None
    scored: List[Tuple[float, int]] = []
    for item in candidates:
        idx = item["i"]
        fp = item.get("fp")
        if not fp:
            continue
        s = similarity_score(stored, fp)
        scored.append((s, idx))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best_score, best_idx = scored[0]
    if best_score < threshold:
        return None
    if len(scored) > 1 and scored[1][0] >= best_score - 0.01:
        return None
    locator = page.locator("body *").nth(best_idx)
    try:
        handle = await locator.element_handle()
        return handle
    except Exception:
        return None
