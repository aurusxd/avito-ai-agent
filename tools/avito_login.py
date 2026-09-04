from playwright.sync_api import sync_playwright


def get_avito_session():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Navigate to your login page
        page.goto("https://avito.ru")

        print("Press enter after login")
        page.pause()

        # Save the session storage and cookies to a file
        context.storage_state(path="state.json")
        print("Session state saved successfully to state.json")

        browser.close()
