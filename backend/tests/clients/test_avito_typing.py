from app.clients.avito.playwright_client import PlaywrightAvitoClient


class StubLocator:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.selected = False
        self.actions: list[str] = []

    async def click(self) -> None:
        self.actions.append("click")

    async def input_value(self) -> str:
        return self.value

    async def press(self, key: str) -> None:
        self.actions.append(f"press:{key}")
        if key == "Control+a":
            self.selected = True
        elif key == "Delete" and self.selected:
            self.value = ""
            self.selected = False

    async def press_sequentially(self, text: str, delay: float = 0) -> None:
        self.actions.append(f"type:{len(text)}")
        self.value += text


class StubPage:
    def __init__(self, prefilled: str = "") -> None:
        self.composer = StubLocator(prefilled)
        self.waited: list[int] = []

    def locator(self, selector: str) -> StubLocator:
        return self.composer

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waited.append(milliseconds)


async def type_into(prefilled: str, text: str) -> StubPage:
    page = StubPage(prefilled)
    await PlaywrightAvitoClient()._type_like_human(page, text)  # type: ignore[arg-type]
    return page


async def test_prefilled_composer_is_cleared_before_typing() -> None:
    text = "Подскажите, баня под ключ ещё актуальна?"

    page = await type_into("Здравствуйте! ", text)

    assert page.composer.value == text
    assert "press:Control+a" in page.composer.actions
    assert "press:Delete" in page.composer.actions


async def test_empty_composer_is_not_cleared() -> None:
    text = "Здравствуйте!"

    page = await type_into("", text)

    assert page.composer.value == text
    assert not any(action.startswith("press:") for action in page.composer.actions)


async def test_whitespace_only_composer_is_cleared_too() -> None:
    page = await type_into("   ", "Здравствуйте!")

    assert page.composer.value == "Здравствуйте!"


async def test_composer_is_clicked_before_typing() -> None:
    page = await type_into("Здравствуйте! ", "Текст")

    assert page.composer.actions[0] == "click"
    assert page.composer.actions[-1].startswith("type:")
    assert page.waited
