# -*- coding: utf-8 -*-
"""Source registry. Add a new scraper here to have it picked up automatically."""

from .amd import AmdSource
from .base import SeenStore, Source
from .dmxapi import DmxapiSource
from .modelscope import ModelScopeSource
from .nvidia import NvidiaSource

SOURCES = [NvidiaSource, AmdSource, ModelScopeSource, DmxapiSource]

__all__ = [
    "AmdSource",
    "DmxapiSource",
    "ModelScopeSource",
    "NvidiaSource",
    "SeenStore",
    "Source",
    "SOURCES",
]
