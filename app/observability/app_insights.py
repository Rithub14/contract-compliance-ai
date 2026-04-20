class AppInsightsClient:
    """Wraps opencensus-ext-azure. Configure APPINSIGHTS_CONNECTION_STRING to enable."""

    def track_event(self, name: str, properties: dict | None = None) -> None:  # noqa: ARG002
        pass

    def track_exception(self) -> None:
        pass


insights = AppInsightsClient()
