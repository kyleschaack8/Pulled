# Pulled: Project Overview

*Last updated Nov 1, 2026*

Pulled is a SaaS app that tracks sports card prices and explains **why** they move, by connecting prices to player performance, injuries and news.

**One-line pitch:** Other apps tell you what your card is worth. Pulled tells you why, and what could move it next.

## The problem

Collectors watch games in one app and check card prices in another, then guess at the connection. Dozens of scanner apps (CollX, Ludex, Card Ladder, Market Movers and many newer AI scanners) answer "what's it worth?" None of them explain why it changed.

## Core features

| Feature | What it does |
| --- | --- |
| Scan any card | Photo in, card identified (player, set, parallel, grade), added to your collection |
| Card page | Price chart with games, injuries and trades marked on the line; sales volume; key stats |
| Why it moved | One plain-English sentence explaining each price change, written automatically |
| Player page | Team, position, current and career stats, projections, injury updates, summary, every card sorted by value with filters |
| Combined player trend | One % for all of a player's cards, weighted by how often each sells (so one rare sale can't skew it), with rookie / graded / raw breakdown |
| Compare cards | Up to 5 cards on one chart: price, sales volume, graded population; % change or actual; side-by-side stats table |
| Retired players | Career stats, legacy rank, Hall of Fame status; chart markers for HOF news, anniversaries, record chases |
| Alerts | News-based alerts on your own cards ("listed questionable — 3 of your cards may be affected") |
| What to watch | Forward-looking calendar of events that could move prices |

## What makes it different

1. Price and performance on one chart
2. "Why it moved" explanations
3. Full player profiles next to the cards
4. Player-wide card market index
5. Looks ahead, not just back
6. Built for everyday collectors, not just investors
7. Covers every sport, active and retired players

Table stakes we match (not why people choose us): scanning, price lookups, collection value, basic price history.

## Brand

- **Name:** Pulled (working name). "What'd you pull?" is universal hobby language across every sport.
- **To check before committing:** pulled.app domain, @pulled / @pulledcards handles, App Store, USPTO trademark search.
- **Look:** dark, sleek, modern. Near-black background, electric lime accent, Inter Tight + IBM Plex Mono.

## Pricing (suggested)

| Plan | Price | Includes |
| --- | --- | --- |
| Rookie | Free | Track up to 50 cards, player pages, current prices, 30-day history |
| All-Star | $7.99 / month | Unlimited cards, "why it moved," full history, compare, alerts, what-to-watch calendar |
| Hall of Fame | $19.99 / month | Everything + bulk scanning, CSV export, advanced data; for dealers and shops |

Other revenue: eBay affiliate links, grading company referrals.

## Running it automatically (SaaS)

| Part | How it runs on its own |
| --- | --- |
| Card prices | Scheduled job pulls new sales nightly from a licensed data source |
| Stats, injuries, news | Sports data API (e.g., Sportradar, SportsDataIO) |
| "Why it moved" | AI matches price changes to recent games and news and writes the summary |
| Scanning + card images | CardSight AI (identification, catalog images, sales, graded population) |
| Alerts | Automatic push/email when news or prices affect a user's cards |
| Billing | Stripe subscriptions, trials, receipts, failed payments |
| Onboarding + newsletter | Automated email sequences; weekly Market Movers auto-generated from data |
| Support | Help center + AI chat assistant |

About 90% automatable. Plan a few hours a week for fixing misidentified cards, harder support questions and marketing. Biggest ongoing cost: data licensing.

## Data and image providers

**Chosen: [CardSight AI](https://pypi.org/project/cardsightai/)** — catalog images, multi-card identification with slab detection, completed sales, active listings, graded population. Free tier: 750 calls/month (no credit card). Paid: Starter from $14.95/mo (5,000 calls), Ultra $199.95/mo (100,000 calls).

Before relying on it: confirm in writing that images may be displayed in a paid commercial app; test accuracy on 10–20 real cards including tricky parallels; confirm sport coverage.

- Free checklist data: [Cardlists (JunkWaxData)](https://awesome.ecosyste.ms/projects/github.com%2Fjunkwaxdata%2Fcardlists), MIT license, mostly baseball.
- Backup identification: Ximilar.
- Never copy images from Google, eBay or card company sites.

The API key lives only on the server (never in website code). Images are fetched once per card and cached.

## Go-to-market

Validate with content first: 4 weeks of free "Card Market Movers" posts (see [content-plan.md](content-plan.md)). If people follow and ask about their own cards, build the web version, then add scanning and alerts.

## Build plan

The test site in this repo grows one piece at a time. See the **Build log** page in the app for what's built and what's next.

Built (v0.2): navigation and search, player pages (active + retired), combined player trend, card pages, auto-written "why it moved," compare tool, collection, card artwork + photo upload.

Next: connect CardSight AI → scanning → real price data → live stats and injuries → alerts → accounts → subscriptions → more sports.
