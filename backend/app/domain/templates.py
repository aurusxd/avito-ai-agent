import re

PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")
KNOWN_PLACEHOLDERS = ("name", "product", "category")


def render_template(template_text: str, *, name: str, product: str, category: str) -> str:
    values = {"name": name, "product": product, "category": category}

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return PLACEHOLDER_PATTERN.sub(substitute, template_text)


def missing_placeholders(template_text: str) -> set[str]:
    found = set(PLACEHOLDER_PATTERN.findall(template_text))
    return found - set(KNOWN_PLACEHOLDERS)
