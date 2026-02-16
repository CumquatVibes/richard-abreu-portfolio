# Cumquat Vibes Shopify Store — Setup Instructions

All code files are in this `shopify-theme/` directory. Paste each file into
the corresponding location in your Shopify theme editor.

**How to access**: Online Store > Themes > Actions > Edit code

---

## PHASE 1: Quick Fixes

### Step 1.1 — Softer Orange Colors
1. In Theme Customizer (Online Store > Themes > Customize), go to Theme Settings > Colors
2. Find the color scheme using the bright orange and update:
   - Orange gradient start → `#f4b88a`
   - Orange gradient end → `#fef5e7`
   - Accent → `#e8941f`

### Step 1.2 — CSS Overrides (colors, popup sizing, fonts)
1. In Edit Code, go to **Assets** folder
2. Click "Add a new asset" > Create blank file > name it `custom-overrides.css`
3. Paste the contents of `assets/custom-overrides.css`
4. Open `layout/theme.liquid`, find `</head>`
5. Add this line BEFORE `</head>`:
   ```
   {{ 'custom-overrides.css' | asset_url | stylesheet_tag }}
   ```

### Step 1.3 — Fix YouTube Thumbnail
Find the video section on your homepage (in Theme Customizer). Try:
- Re-entering the YouTube URL in the section settings
- If still broken, the `custom-overrides.css` above includes fixes

### Step 1.4 — Fix Welcome Popup
- **If it's a theme popup**: The CSS overrides above fix the sizing
- **If it's a Klaviyo popup**: Go to Klaviyo > Forms > select the form > adjust width to 400px max

---

## PHASE 2: Navigation & Pages

### Step 2.1 — Update Navigation
1. Go to Online Store > Navigation > Main menu
2. Add these menu items:
   - **Shop** (link to `/collections/all`)
     - Under Shop, add nested items: Wall Art, Apparel, Drinkware (link each to their collection)
   - **Blog** (link to `/blogs/news`)
   - **YouTube** (link to `/pages/youtube` — create the page first, see 2.2)

### Step 2.2 — Create YouTube Page
1. **Create the section file**:
   - Edit Code > Sections > Add new section > name it `custom-youtube-gallery`
   - Paste contents of `sections/custom-youtube-gallery.liquid`
2. **Create the CSS file**:
   - Edit Code > Assets > Add new asset > Create blank > name it `custom-youtube-gallery.css`
   - Paste contents of `assets/custom-youtube-gallery.css`
3. **Create the page template**:
   - Edit Code > Templates > Add new template > Type: page, name: youtube
   - Paste contents of `templates/page.youtube.json`
4. **Create the page**:
   - Go to Online Store > Pages > Add page
   - Title: "YouTube"
   - In right sidebar, under Theme template, select `page.youtube`
5. **Configure**:
   - Go to Theme Customizer, navigate to the YouTube page
   - In the YouTube Gallery section settings, enter your API Key and Channel ID

### Step 2.3 — richardabreu.studio Links
1. **Announcement Bar**: In Theme Customizer > Announcement bar, set text to
   "Designs by Richard Abreu Studio" with link to `https://richardabreu.studio`
2. **Footer Badge**: See layout/theme.liquid additions below (Phase 4)

---

## PHASE 3: Homepage Sections

For each section below:
1. Go to Edit Code > Sections > Add new section
2. Name it exactly as shown (without .liquid)
3. Paste the file contents
4. Go to Theme Customizer > Homepage > Add section to place it

### Sections to Create (in recommended homepage order):

| Create Section Named         | Paste From                                          | Customizer Name       |
|------------------------------|-----------------------------------------------------|-----------------------|
| `custom-hero-banner`         | `sections/custom-hero-banner.liquid`                | Custom Hero Banner    |
| `custom-value-proposition`   | `sections/custom-value-proposition.liquid`           | Value Proposition     |
| `custom-rotating-collections`| `sections/custom-rotating-collections.liquid`        | Rotating Collections  |
| `custom-artist-spotlight`    | `sections/custom-artist-spotlight.liquid`            | Artist Spotlight      |
| `custom-seasonal-highlight`  | `sections/custom-seasonal-highlight.liquid`          | Seasonal Highlight    |
| `custom-featured-products-rotation` | `sections/custom-featured-products-rotation.liquid` | Featured Products Rotation |
| `custom-testimonials`        | `sections/custom-testimonials.liquid`                | Testimonials          |
| `custom-youtube-preview`     | `sections/custom-youtube-preview.liquid`             | YouTube Preview       |
| `custom-blog-preview`        | `sections/custom-blog-preview.liquid`                | Blog Preview          |
| `custom-recently-viewed`     | `sections/custom-recently-viewed.liquid`             | Recently Viewed       |

### Additional CSS Files (Assets):
| Create Asset Named               | Paste From                                    |
|----------------------------------|-----------------------------------------------|
| `custom-hero-banner.css`         | `assets/custom-hero-banner.css`               |
| `custom-rotating-collections.css`| `assets/custom-rotating-collections.css`       |

### Create Collections:
1. Go to Products > Collections
2. Create: **Best Sellers** (manual, add your top products)
3. Create: **New Arrivals** (automated, sort by newest)
4. Use Shopify's built-in "Featured collection" section for these on the homepage

### Recommended Homepage Section Order:
1. Announcement Bar (richardabreu.studio)
2. Header
3. Custom Hero Banner ← upload a lifestyle image
4. Value Proposition ← trust badges
5. Best Sellers (built-in Featured Collection)
6. Rotating Collections ← add all your collections as blocks
7. Artist Spotlight ← upload your photo, write bio
8. Seasonal Highlight ← set end date, upload seasonal image
9. Featured Products Rotation ← add source collections as blocks
10. Testimonials ← add customer quotes as blocks
11. YouTube Preview ← add 3-4 video IDs as blocks
12. Blog Preview ← select your "News" blog
13. New Arrivals (built-in Featured Collection)
14. Recently Viewed
15. Newsletter (existing)
16. Footer

---

## PHASE 4: Conversion Features

### Step 4.1 — Create Snippets
In Edit Code > Snippets, create each:

| Create Snippet Named          | Paste From                                    |
|-------------------------------|-----------------------------------------------|
| `free-shipping-bar`           | `snippets/free-shipping-bar.liquid`            |
| `exit-intent-popup`           | `snippets/exit-intent-popup.liquid`            |
| `purchase-notifications`      | `snippets/purchase-notifications.liquid`       |
| `product-urgency`             | `snippets/product-urgency.liquid`              |
| `quick-view`                  | `snippets/quick-view.liquid`                   |

### Step 4.2 — Add to layout/theme.liquid
Open `layout/theme.liquid` and make these additions:

**In `<head>` (after existing stylesheets):**
```liquid
{{ 'custom-overrides.css' | asset_url | stylesheet_tag }}
<link rel="preconnect" href="https://cdn.shopify.com" crossorigin>
<link rel="dns-prefetch" href="https://cdn.shopify.com">
```

**Before `</body>` (at the very end):**
See `layout/THEME-LIQUID-ADDITIONS.liquid` for the exact code to paste.
It includes: exit-intent popup, purchase notifications, quick-view modal,
sticky mobile CTA, and richardabreu.studio footer badge.

### Step 4.3 — Free Shipping Bar in Cart
Find your cart section (likely `sections/cart-drawer.liquid` or `sections/main-cart-items.liquid`)
Add near the top of the cart content area:
```liquid
{% render 'free-shipping-bar' %}
```

### Step 4.4 — Urgency Badges on Products
Find your product section (likely `sections/main-product.liquid`)
Add above the Add to Cart button:
```liquid
{% render 'product-urgency', product: product %}
```
Then tag products in Shopify Admin with: `limited-edition`, `best-seller`, or `new-arrival`

### Step 4.5 — Create Discount Code
Go to Discounts > Create discount:
- Code: `WELCOME10`
- Type: Percentage, 10% off
- Applies to: Entire order
- Usage limit: 1 per customer

---

## PHASE 5: Advanced Features

### Step 5.1 — Style Quiz (Interactive Product Finder)

This is a 5-step interactive quiz that matches visitors to their ideal art style and recommends products.

**Create the section file:**
1. Edit Code > Sections > Add new section > name it `custom-style-quiz`
2. Paste contents of `sections/custom-style-quiz.liquid`

**Create the page template:**
1. Edit Code > Templates > Add new template > Type: page, name: style-quiz
2. Paste contents of `templates/page.style-quiz.json`

**Create the page:**
1. Go to Online Store > Pages > Add page
2. Title: "Find Your Style" (or "Style Quiz")
3. In right sidebar, under Theme template, select `page.style-quiz`
4. Save and publish

**Add to navigation:**
1. Go to Online Store > Navigation > Main menu
2. Add menu item: "Style Quiz" → `/pages/find-your-style` (or whatever slug you used)

**Tag your products for quiz matching:**
The quiz searches for products by tags. Add these tags to your products in Products > [product] > Tags:

| Tag Type | Options | Example |
|----------|---------|---------|
| Style | `style-modern`, `style-bohemian`, `style-minimalist`, `style-bold` | A clean geometric print → `style-modern`, `style-minimalist` |
| Palette | `palette-warm`, `palette-cool`, `palette-neutral`, `palette-vibrant` | Sunset-themed art → `palette-warm`, `palette-vibrant` |
| Mood | `mood-calm`, `mood-energetic`, `mood-cozy`, `mood-dramatic` | Ocean landscape → `mood-calm` |
| Budget | `budget-under-50`, `budget-50-100`, `budget-100-plus` | Based on product price range |

The more tags you add per product, the better the quiz matching. Each product should have at least one tag from each category.

**Quiz style profiles:**
- **The Contemporary Curator** — modern + minimalist preferences
- **The Free Spirit** — bohemian + warm/vibrant preferences
- **The Quiet Connoisseur** — minimalist + cool/neutral preferences
- **The Statement Maker** — bold + vibrant/dramatic preferences

**Customize in Theme Customizer:**
Navigate to the Style Quiz page in the customizer to adjust:
- Question text for each of the 5 steps
- Accent color and background color
- Maximum number of product results (default: 6)

---

### Step 5.2 — Instagram Feed (Manual Post Grid)

A visual Instagram-style grid with hover captions and link-through to your posts.

**Create the section file:**
1. Edit Code > Sections > Add new section > name it `custom-instagram-feed`
2. Paste contents of `sections/custom-instagram-feed.liquid`

**Add to homepage:**
1. Go to Theme Customizer > Homepage > Add section
2. Select "Instagram Feed"
3. Configure:
   - **Heading**: "Follow Along @cumquatvibes" (or your preferred text)
   - **Instagram URL**: `https://instagram.com/cumquatvibes`
   - **Posts to show**: 6 (recommended) or 3-12
   - **CTA text**: "Follow on Instagram"

**Add Instagram posts as blocks:**
1. In the section settings, click "Add block" > "Instagram Post"
2. For each post:
   - **Image**: Upload or select the Instagram post image from your media library
   - **Caption**: Short caption text (shown on hover)
   - **Link**: Direct URL to that Instagram post (e.g., `https://instagram.com/p/ABC123/`)
3. Repeat for each post you want to display (6-12 recommended)

**Tips:**
- Save your best-performing Instagram images to your Shopify media library
- Update posts monthly to keep the feed fresh
- The grid automatically handles responsive layout (3 cols desktop, 2 tablet, 1 mobile)
- Posts animate in with a staggered fade effect on scroll

---

### Step 5.3 — Gift Guide (Tabbed Category Browser)

A tabbed interface letting shoppers browse gift ideas by category (For Her, For Him, Under $50, etc.).

**Create collections first:**
1. Go to Products > Collections
2. Create these collections (or use your own categories):

| Collection Title | Suggested Products |
|------------------|--------------------|
| Gifts for Her | Floral prints, warm-toned art, cozy drinkware |
| Gifts for Him | Bold geometric art, dark-toned prints, tech accessories |
| Gifts for Home | Wall art sets, large canvases, matching print pairs |
| Gifts Under $50 | Smaller prints, mugs, stickers, phone cases |
| Art Lover Gifts | Premium prints, limited editions, artist series |

**Create the section file:**
1. Edit Code > Sections > Add new section > name it `custom-gift-guide`
2. Paste contents of `sections/custom-gift-guide.liquid`

**Add to homepage (or a dedicated page):**
1. Go to Theme Customizer > Homepage > Add section
2. Select "Gift Guide"
3. Configure:
   - **Heading**: "Gift Guide" (or "Find the Perfect Gift")
   - **Subheading**: Optional descriptive text

**Add category tabs as blocks:**
1. Click "Add block" > "Gift Category"
2. For each category:
   - **Tab title**: e.g., "For Her"
   - **Icon**: An emoji like 🎀, 👔, 🏠, 💰, 🎨
   - **Collection**: Select the matching collection you created
   - **Products to show**: 4-8 (4 recommended for clean grid)
   - **Show "View collection" link**: Enable to add a link to the full collection
3. Add up to 8 category tabs

**Features included:**
- Full keyboard navigation (Arrow keys, Home/End between tabs)
- ARIA-compliant tablist for screen readers
- Sale badges auto-calculated from compare-at prices
- Responsive grid: 4 columns (desktop) → 2 (tablet) → 1 (mobile)
- Smooth fade animation on tab switch

---

## Verification Checklist

- [ ] Orange colors appear softer/pastel across the site
- [ ] Welcome popup is properly sized on mobile and desktop
- [ ] YouTube video thumbnail displays correctly
- [ ] Navigation shows: Home, Shop (dropdown), Blog, YouTube, Catalog, Contact
- [ ] YouTube page loads videos from your channel
- [ ] Hero banner shows with lifestyle image and CTA
- [ ] Value proposition bar shows 4 trust badges
- [ ] Collections rotate automatically
- [ ] Featured products pull from multiple collections
- [ ] Artist Spotlight section shows your photo and bio
- [ ] Seasonal section shows countdown timer
- [ ] Testimonials display with star ratings
- [ ] YouTube preview shows 3-4 video thumbnails
- [ ] Blog preview shows latest 3 posts
- [ ] Recently Viewed shows after browsing products
- [ ] Free shipping bar appears in cart
- [ ] Exit-intent popup shows once for new visitors
- [ ] Purchase notifications appear periodically
- [ ] Sticky "Shop Now" bar visible on mobile
- [ ] richardabreu.studio link in announcement bar and footer
- [ ] All pages load without console errors

### Phase 5 Verification
- [ ] Style Quiz page loads at `/pages/find-your-style`
- [ ] Quiz advances through all 5 steps (style → palette → room → mood → budget)
- [ ] Quiz shows a style profile result with product recommendations
- [ ] Quiz product search returns tagged products (add tags to at least 5 products to test)
- [ ] Quiz "Retake Quiz" button resets to step 1
- [ ] Instagram Feed section displays post images in a grid
- [ ] Instagram hover overlay shows caption text (desktop)
- [ ] Instagram CTA button links to your Instagram profile
- [ ] Gift Guide tabs switch between categories
- [ ] Gift Guide keyboard navigation works (Arrow keys between tabs)
- [ ] Gift Guide shows products from the correct collection per tab
- [ ] Gift Guide sale badges display when products have compare-at prices
- [ ] All Phase 5 sections are responsive on mobile
