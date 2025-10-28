
from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch()
    page = browser.new_page()

    # Login first
    page.goto("http://127.0.0.1:5000/login")
    page.fill("input[name='username']", "admin")
    page.fill("input[name='password']", "password")
    page.click("button[type='submit']")
    page.wait_for_url("http://127.0.0.1:5000/")

    # Navigate to results and take screenshot
    page.goto("http://127.0.0.1:5000/results")
    page.screenshot(path="jules-scratch/verification/results.png")

    # Navigate to dashboard and take screenshot
    page.goto("http://127.0.0.1:5000/dashboard")
    page.screenshot(path="jules-scratch/verification/dashboard.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
