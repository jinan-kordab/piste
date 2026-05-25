# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
SQLAlchemy Base — Declarative base for all models.
All stage_records and verdicts tables are APPEND-ONLY (no UPDATE/DELETE).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass
