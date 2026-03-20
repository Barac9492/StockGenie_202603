# TODOS — QuantRadar

## P1 — High Priority (post-MVP)

### VPS Deployment + HTTPS
Move from local Mac to always-on VPS for 24/7 dashboard access from phone.
Includes systemd service, nginx reverse proxy, Let's Encrypt SSL.
- **Effort:** S (human ~4hrs / CC ~20min)
- **Depends on:** MVP running locally + validated
- **Why:** Needed for mobile access goal — can't check dashboard from phone without remote hosting

## P2 — Medium Priority

### KIS Developers API Integration
Add KIS (한국투자증권) API for real-time intraday Korean stock data.
Currently using pykrx for daily data — KIS unlocks 30분 간격 업데이트.
- **Effort:** M (human ~1 week / CC ~30min)
- **Depends on:** MVP completion + KIS developer account setup/approval
- **Why:** PRD requires 장 중 30분 간격 signal updates; pykrx only provides end-of-day data

### Portfolio Tracking
Track actual holdings, purchase price, current P&L.
Connect with decision journal to show signal→action→outcome chain.
- **Effort:** M (human ~1 week / CC ~30min)
- **Depends on:** MVP + journal feature working
- **Why:** PRD P1 feature; closes the loop from "I got a signal" to "here's my actual return"

## P3 — Nice to Have

### Full DESIGN.md via /design-consultation
Create a proper design system document covering component library, animation guidelines,
icon system, and brand voice. Current inline specs (colors, typography, spacing) are
sufficient for MVP but a formal DESIGN.md helps maintain consistency as the app grows.
- **Effort:** S (CC ~15min)
- **Depends on:** MVP running with current inline design specs
- **Why:** Inline specs cover basics but don't formalize component patterns or brand voice

### Mobile Sidebar Override
Streamlit sidebar auto-expands on mobile viewports, covering the main content.
Requires custom CSS injection (`st.markdown` with `<style>`) to force collapsed state on narrow screens.
- **Effort:** S (human ~2hrs / CC ~10min)
- **Depends on:** MVP running
- **Why:** Design review FINDING-004 — mobile usability issue
- **Source:** /design-review on feat/quantradar-mvp, 2026-03-20

### 카카오톡 알림톡
Add Kakao push notifications for time-sensitive signals (especially sell signals).
More immediate than email for urgent actions.
- **Effort:** M (human ~1 week / CC ~30min)
- **Depends on:** Email digest working + Kakao Developer account
- **Why:** Original PRD requirement; email may not be fast enough for intraday sell signals
