from hypothesis import given
from hypothesis import strategies as st

from app.domain.templates import missing_placeholders, render_template

safe_text = st.text(alphabet=st.characters(blacklist_characters="{}"), min_size=1, max_size=40)


def test_render_template_substitutes_known_placeholders() -> None:
    result = render_template(
        "Здравствуйте, {name}! Ваш «{product}» в «{category}»?",
        name="Артём",
        product="баня-бочка",
        category="Бани",
    )

    assert result == "Здравствуйте, Артём! Ваш «баня-бочка» в «Бани»?"


def test_render_template_keeps_unknown_placeholders() -> None:
    result = render_template("{name} {unknown}", name="Ольга", product="x", category="y")

    assert result == "Ольга {unknown}"
    assert missing_placeholders("{name} {unknown}") == {"unknown"}


@given(name=safe_text, product=safe_text, category=safe_text)
def test_render_template_leaves_no_known_placeholder(
    name: str, product: str, category: str
) -> None:
    template = "{name}|{product}|{category}"

    result = render_template(template, name=name, product=product, category=category)

    assert result == f"{name}|{product}|{category}"
    assert "{name}" not in result
    assert "{product}" not in result
    assert "{category}" not in result


@given(text=safe_text)
def test_render_template_without_placeholders_is_identity(text: str) -> None:
    assert render_template(text, name="a", product="b", category="c") == text
