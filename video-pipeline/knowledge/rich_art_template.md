# Rich Art TV — "Turn Your TV Into Art" Template

## Research Date: February 23, 2026
## Source: User feedback on https://youtu.be/T9BgTPUSnFo

---

## TITLE TEMPLATE

Format: `{Theme/Artists} | Turn Your TV Into Art | {Duration} 4K Slideshow`

Examples:
- Impressionist Masterpieces – Monet, Renoir & Degas | Turn Your TV Into Art | 1Hr 4K Slideshow
- Vintage Garden Paintings | Turn Your TV Into Art | 1Hr 4K Slideshow
- Abstract Color Fields | Turn Your TV Into Art | 1Hr 4K Slideshow
- Holiday Snowy Villages | Turn Your TV Into Art | 1Hr 4K Slideshow
- Anime-Style City Nights | Turn Your TV Into Art | 1Hr 4K Slideshow

---

## DESCRIPTION TEMPLATE

```
Transform your space with this {theme} collection in stunning 4K, perfect as ambient art for your TV, living room, office, cafe, or studio background.

▶ What you get
- {duration} of continuous {theme} artwork
- Optimized for 4K TVs and smart displays
- Ideal for relaxing, studying, working, or entertaining guests

▶ Featuring
- Artists: {Monet, Renoir, Degas or theme-specific list}
- Style: {Impressionism / Vintage / Abstract / Holiday / etc.}

▶ Get matching prints and merch
Bring this art off the screen and into your home with high-quality prints, apparel, and accessories:
https://www.cumquatvibes.com

Browse more of my artwork and projects:
Portfolio: https://richardabreu.studio
Community & updates: https://vibeconnectionlounge.com

▶ How to use this video
- Set as background art while you relax, read, or host guests
- Use on a second monitor while working or studying
- Play in lobbies, cafes, salons, or offices for a calm, creative vibe

▶ About this project
This video was created using curated and AI-assisted artwork, edited and compiled by a human artist to deliver a unique viewing experience.

Thank you for watching and supporting independent creators!
```

---

## TAGS (10-15 max, mix broad + niche)

Base tags (always include):
- art for tv, tv wall art, 4k art, 4k slideshow, ambient video, relaxing art, art slideshow, wall art video, living room tv art, frame tv art, background art

Theme-specific additions:
- Impressionist: impressionist art, monet, renoir, degas
- Garden: vintage art, garden paintings, floral art, nature paintings
- Abstract: abstract art, modern art, color field
- Holiday: holiday art, christmas paintings, snowy villages

---

## VIDEO STRUCTURE

1. **Intro card** (3-5 sec): Logo + "Turn Your TV Into Art – {Theme} Collection"
2. **Main slideshow** (~59:30): Long uninterrupted slideshow with very slow transitions
3. **End card** (5-10 sec): "Subscribe for more Art for Your TV" + Cumquat Vibes URL + logo

---

## SERIES SYSTEM

Playlist name: "Turn Your TV Into Art – Collections"

Planned episodes:
- [x] Impressionist Masterpieces (uploaded)
- [x] Van Gogh Complete Collection (uploaded)
- [x] Japanese Woodblock Prints (uploaded)
- [ ] Vintage Garden Paintings (in production)
- [ ] Abstract Color Fields
- [ ] Holiday Snowy Villages
- [ ] Anime-Style City Nights
- [ ] Coastal Seascapes
- [ ] Renaissance Masterpieces – Da Vinci to Raphael
- [ ] Monet's Water Lilies
- [ ] Baroque Grandeur
- [ ] Cozy Cottage Art
- [ ] Mountain Vistas
- [ ] Art Deco Elegance

---

## COPYRIGHT COMPLIANCE

### Safe Sources (CC0 / Open Access)
1. **The Metropolitan Museum of Art** — 400K+ works, CC0, free API
2. **Rijksmuseum** — 700K+ works, public domain, API key required
3. **Art Institute of Chicago** — 100K+ works, CC0, free API
4. **National Gallery of Art** — 50K+ images, public domain
5. **Getty Museum** — 88K+ works, CC0
6. **Smithsonian Open Access** — 3M+ items, CC0

### Rules
- ONLY use images from sources with explicit CC0/public domain commercial use
- Create asset log for every video (source URL + license per image)
- Alternative: Use AI-generated "in the style of" paintings (100% safe)
- Modern photos of old paintings CAN be copyrighted — always check the photo license
- Add AI disclosure: "This video was created using curated and AI-assisted artwork"

### Asset Log Format
```
# Asset License Log - {Theme}
# Generated: {date}
# Total assets: {count}
# All images: CC0 from {source}
# Commercial use: ALLOWED

- {Title} by {Artist} ({Date})
  Source: {URL}
  License: CC0 - {Source Organization}
```

---

## PIPELINE INTEGRATION

The art template is implemented in:
- `upload_to_youtube.py`: `_make_art_description()` function
- `upload_to_youtube.py`: `make_title()` — RichArt format detection
- `upload_to_youtube.py`: `ART_SLIDESHOW_CHANNELS` set
- `utils/ambient.py`: `assemble_art_slideshow()` for 4K assembly
- `utils/broll.py`: `RichArt` B-roll template for AI-generated alternatives
