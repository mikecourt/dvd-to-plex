"""Tests for US-010: Verify web app can start.

These tests verify that the web application can be imported and created
without errors, confirming the basic setup is correct.
"""

import inspect

from fastapi import FastAPI

from dvdtoplex.web.app import create_app


def test_create_app_can_be_imported() -> None:
    """Verify create_app can be imported from dvdtoplex.web.app."""
    assert create_app is not None
    assert callable(create_app)


def test_create_app_returns_fastapi_instance() -> None:
    """Verify create_app returns a FastAPI application instance."""
    app = create_app()
    assert isinstance(app, FastAPI)


def test_create_app_has_no_required_parameters() -> None:
    """Verify create_app signature has no required parameters."""
    sig = inspect.signature(create_app)
    # All parameters should have defaults (no required params)
    for param in sig.parameters.values():
        assert param.default != inspect.Parameter.empty or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ), f"Parameter {param.name} has no default value"


def test_create_app_signature_parameters() -> None:
    """Verify and document the create_app function signature."""
    sig = inspect.signature(create_app)
    param_names = list(sig.parameters.keys())
    # Document what parameters exist (optional database, drive_watcher, config)
    # This test serves to catch changes to the signature
    expected_params = ["database", "drive_watcher", "config"]
    assert param_names == expected_params, f"Expected {expected_params}, got: {param_names}"


def test_app_has_routes() -> None:
    """Verify the created app has routes configured."""
    app = create_app()
    # FastAPI apps should have at least some routes
    assert len(app.routes) > 0, "App should have routes configured"
