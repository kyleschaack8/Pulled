# Pulled

Sports card prices, explained. Pulled tracks card prices next to player stats, injuries and news, and tells you in plain English why your cards move.

**Live test site:** https://kyleschaack8.github.io/Pulled/ (sample data)
**Landing page:** https://kyleschaack8.github.io/Pulled/landing/

## What's in this repo

| Path | What it is |
| --- | --- |
| `index.html` | The working test app (v0.2, sample data): player pages, card pages, compare, collection, build log |
| `landing/index.html` | Marketing website with waitlist form (form doesn't save emails yet) |
| `docs/PROJECT.md` | Business overview: concept, features, pricing, automation plan, data providers |
| `docs/content-plan.md` | 4-week "Card Market Movers" content plan to validate demand |
| `docs/mockups/` | Design canvas source files for the app screens and website |
| `tools/get_card_images.py` | Downloads card images from CardSight AI. Needs your own `CARDSIGHTAI_API_KEY` |

## Rules for this repo

- Never commit API keys or passwords. `.gitignore` blocks `.env` files and downloaded images.
- All prices and stats in the test site are illustrative sample data.

## Status

Built: navigation and search, player pages (active + retired), combined player trend, card pages with event markers, auto-written "why it moved," compare tool, collection, card artwork and photo upload.

Next: connect CardSight AI for real card images and scanning.
