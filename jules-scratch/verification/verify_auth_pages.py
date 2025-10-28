from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto("http://127.0.0.1:5000/login")
    page.screenshot(path="jules-scratch/verification/login_page.png")
    page.goto("http://127.0.0.1:5000/register")
    page.screenshot(path="jules-scratch/verification/register_page.png")
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
