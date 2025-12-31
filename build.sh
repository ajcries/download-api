#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install python dependencies
pip install -r requirements.txt

# Install Playwright browser and its system dependencies
playwright install chromium --with-deps