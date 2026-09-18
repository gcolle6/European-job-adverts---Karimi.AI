"""Karimi.ai — same title, different job.

Measuring how much a role's requirement profile changes with the context it sits
in, and separating the invariant core from the context-specific shell.

Modules
-------
``config``        committed thresholds, the analytical grid, paths
``data``          loading and the exclusion chain that produces the analysis base
``audit``         descriptive checks: coverage, cell counts, employer concentration
``atomise``       splitting compound requirements into single units
``classify``      six-way requirement typing via a multilingual lexicon
``requirements``  the requirement table and its summaries

Typical use::

    from karimi import data, requirements

    base = data.build_analysis_base()
    reqs = requirements.classify_requirements(
        requirements.build_requirement_table(base.df)
    )
"""

__version__ = "0.1.0"

from . import atomise, audit, checks, classify, config, data, requirements  # noqa: F401

__all__ = ["atomise", "audit", "checks", "classify", "config", "data", "requirements"]
