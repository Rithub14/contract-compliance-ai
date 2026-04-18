class AppInsightsClient:
    """Stub — will wrap opencensus-ext-azure when connection string is configured."""

    def track_event(self, name: str, properties: dict | None = None) -> None:
        pass

    def track_exception(self) -> None:
        pass


insights = AppInsightsClient()
