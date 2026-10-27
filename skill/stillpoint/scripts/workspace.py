"""Bounded workspace resolution; no network, credentials or filesystem mutation."""
import os
from pathlib import Path


def resolve_workspace(explicit=None, cwd=None):
    candidates = [Path(explicit).expanduser()] if explicit else []
    if not explicit:
        configured = os.environ.get('STILLPOINT_WORKSPACE') or os.environ.get('INVEST_BASE')
        if configured:
            candidates.append(Path(configured).expanduser())
        current = Path(cwd or Path.cwd()).resolve()
        candidates.extend([current] + list(current.parents)[:5])
    for item in candidates:
        item = item.resolve()
        if item.name in ('stillpoint-data', 'stillpoint-pages'):
            item = item.parent
        if (item / 'stillpoint-data').is_dir() and (item / 'stillpoint-pages').is_dir():
            return item
    raise ValueError('Set --workspace to a directory containing stillpoint-data and stillpoint-pages')
