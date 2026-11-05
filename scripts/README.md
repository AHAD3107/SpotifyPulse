# Utility & Operational Scripts

This directory contains standalone operational scripts for database initialization, seed data loading, demo dataset generation, and pipeline management.

## Planned Scripts

* `scripts/seed_demo_data.py`: Populate Bronze and Staging with rich synthetic demo listening data.
* `scripts/init_warehouse.py`: Create PostgreSQL schemas (`bronze`, `staging`, `analytics`) and run initial Alembic migrations.
* `scripts/run_pipeline.py`: CLI trigger for manual pipeline execution.

