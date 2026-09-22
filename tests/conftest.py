from __future__ import annotations

import random

import pytest

from animatronic_eyes.config.loader import DEFAULT_CONFIG_PATH, load
from animatronic_eyes.hal.mock import MockBackend
from animatronic_eyes.module.eyes import EyeController


@pytest.fixture
def config():
    """The real shipped configuration -- these tests guard the actual values."""
    return load(DEFAULT_CONFIG_PATH)


@pytest.fixture
def backend():
    return MockBackend()


@pytest.fixture
def eyes(config, backend):
    return EyeController(config, backend)


@pytest.fixture
def rng():
    return random.Random(1234)
