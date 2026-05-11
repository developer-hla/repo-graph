class ThingFormatter:
    def format(self, value: str) -> dict[str, str]:
        return {"label": value}


def format_thing(value: str) -> dict[str, str]:
    return ThingFormatter().format(value)
