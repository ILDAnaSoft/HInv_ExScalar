"""Entry point of the hep_workflows plugin (see pyproject.toml): registers the configurations, so
they are available in law without --module."""


def register():
    import hinv.workflows.fast_k4run  # noqa: F401
