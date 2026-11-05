"""Staging normalization, Pydantic validation, and data cleansing.

Parses raw Bronze JSON files, validates schema contracts, cleans nulls,
normalizes timezones to UTC, and performs idempotent UPSERTs into PostgreSQL staging.
(Implementation scheduled for Phase 4 & 5).
"""

