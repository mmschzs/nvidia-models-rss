# -*- coding: utf-8 -*-
"""Source registry. Add a new scraper here to have it merged into the feed."""

from .amd import AmdSource
from .base import SeenStore, Source
from .nvidia import NvidiaSource

SOURCES = [NvidiaSource, AmdSource]

__all__ = ["AmdSource", "NvidiaSource", "SeenStore", "Source", "SOURCES"]
