
from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto("http://127.0.0.1:5000/login")
    page.screenshot(path="jules-scratch/verification/login_page_grid.png")
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
