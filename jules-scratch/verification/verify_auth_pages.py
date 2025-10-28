from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch()
    page = browser.new_page()

    # Verify login page
    page.goto("http://127.0.0.1:5000/login")
    page.screenshot(path="jules-scratch/verification/login_page_final.png")

    # Verify registration page
    page.goto("http://127.0.0.1:5000/register")
    page.screenshot(path="jules-scratch/verification/register_page_final.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
