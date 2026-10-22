"""Public, curated content; never enumerate private tenant uploads for the portfolio."""

import json
from pathlib import Path

PROJECTS = json.loads(Path(__file__).with_suffix(".json").read_text())
PROFILE = json.loads(Path(__file__).with_name("profile.json").read_text())
PROJECT_BY_SLUG = {p["slug"]: p for p in PROJECTS}
PUBLIC_PAGES = {"/", "/projects", "/tools", "/about", "/resume", "/robots.txt", "/sitemap.xml"}
PUBLIC_PAGES.update("/projects/" + p["slug"] for p in PROJECTS)
SOCIALS = [
    {"name": "GitHub", "url": "https://github.com/stormk-2026", "icon": "github"},
    {"name": "X", "url": "https://x.com/CryptoStormG", "icon": "x"},
    {"name": "Telegram", "url": "https://t.me/StormG0", "icon": "telegram"},
    {"name": "微信", "contact": "wechat", "icon": "wechat"},
    {"name": "邮箱", "contact": "email", "icon": "mail"},
]
