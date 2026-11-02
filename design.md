# Dot Design System: Strictly Black and White Minimalist

This document defines the visual design system, color tokens, typography scales, elevation hierarchy, and component standards for the Dot desktop assistant.

---

## 1. Design Philosophy

1. **Strictly Black and White (Monochrome & Chrome / Silver)**:
   - The interface uses pure blacks, deep charcoals, and graduated zinc shades (`#000000`, `#09090b`, `#121214`, `#18181b`, `#27272a`).
   - Surfaces do not use chromatic colors, pink, purple, or berry tints.
   - Contrast and hierarchy come from white luminances, silver specular ridges, and crisp 1px borders (`rgba(255, 255, 255, 0.08)` to `rgba(255, 255, 255, 0.20)`).
2. **High-Contrast White & Silver Accents**:
   - Primary interactive controls use pure white (`#ffffff`) surfaces with pitch black text.
   - The Dot Core Orb uses a silver chrome radial gradient with a soft white glow.
   - Active tabs, focused borders, and status indicators use solid white and zinc outlines.
3. **No Emojis & No Em Dashes**:
   - The interface uses precision vector geometry (clean 12-14px outline SVGs) instead of Unicode emojis.
   - The interface does not use em dashes. It uses colons, standard hyphens, or spacing.
4. **Impeccable 8-Point Spatial System**:
   - All component dimensions, margins, and paddings adhere strictly to an 8pt modular scale with 4pt half-steps (4, 8, 12, 16, 20, 24, 32px).
5. **Architectural Continuity**:
   - The existing structural foundation (S-curve organic top boundary, Control Shelf, Token Bar, Input Pill, 3-Dots Settings, and bottom-anchored upward expansion) is strictly preserved. Only visual tokens, icons, and styling are upgraded.

---

## 2. Color Palette & Design Tokens

### 2.1 Surfaces & Backgrounds
| Token Name | Hex / RGBA | Role & Usage |
| :--- | :--- | :--- |
| `surface-canvas` | `#09090b` | Host window ambient backdrop |
| `surface-card-start` | `#242427` (0.78 opacity) | Main floating shell gradient start (top-left) |
| `surface-card-mid` | `#1c1c1f` (0.86 opacity) | Main floating shell gradient midpoint |
| `surface-card-end` | `#121214` (0.94 opacity) | Main floating shell gradient end (bottom-right) |
| `surface-control-tier` | `#18181b` (0.80 opacity) | Token Bar & control shelf container fill |
| `surface-input-pill` | `#161618` (0.90 opacity) | Lower input pill background |
| `surface-modal-body` | `#141416` (0.98 opacity) | 3-Dots Settings modal body |
| `surface-modal-header`| `#18181b` (1.00 opacity) | Modal header and navigation tab bar |
| `surface-inset-field` | `#0f0f11` (1.00 opacity) | Text inputs, dropdowns, code badges |

### 2.2 Borders & Dividers
| Token Name | RGBA / Hex | Role & Usage |
| :--- | :--- | :--- |
| `border-card-hairline`| `rgba(255, 255, 255, 0.08)` | Outer container boundary |
| `border-control` | `rgba(255, 255, 255, 0.10)` | Token Bar & pill control boundaries |
| `border-divider` | `rgba(255, 255, 255, 0.06)` | Modal tab separators, shelf dividers |
| `border-focus-white` | `rgba(255, 255, 255, 0.60)` | Focused input pill active boundary |
| `border-active-white`| `#ffffff` | Active tabs and toggled control states |

### 2.3 Typography & Contrast Hierarchy
| Token Name | Hex / RGBA | Role & Hierarchy |
| :--- | :--- | :--- |
| `text-primary` | `#ffffff` | Primary values, input text, headers |
| `text-secondary` | `#d4d4d8` | Subtitles, labels, units, active toggles |
| `text-muted` | `#71717a` | Helper text, placeholder copy, keyboard tags |
| `text-accent-white` | `#ffffff` | Active mode labels, thinking indicator |

### 2.4 Monochromatic Dot Core Orb
```css
/* Chrome & Silver Radial Gradient */
--orb-gradient: radial-gradient(circle at 35% 35%, #ffffff 0%, #e4e4e7 25%, #a1a1aa 50%, #52525b 75%, #18181b 100%);
--orb-glow: 0 0 14px rgba(255, 255, 255, 0.45);
```

### 2.5 Primary Action Button
```css
/* High-Contrast Pure White Button */
--btn-primary-bg: #ffffff;
--btn-primary-text: #000000;
--btn-primary-hover: #e4e4e7;
--btn-primary-active: #d4d4d8;
```

### 2.6 S-Curve Ridge Gradient
```css
/* Luminous Chrome / Specular Ridge */
--scurve-ridge: linear-gradient(90deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.92) 35%, rgba(220,220,230,0.75) 70%, rgba(255,255,255,0.25) 100%);
```

---

## 3. Typography Scale & Fonts

The Dot typography system combines **Inter** for conversational readability and **JetBrains Mono** for metrics, code, and system status:

- **Heading (Modal Titles)**: `Inter`, 13.5px, Weight 600, Line-height 1.3, Letter-spacing -0.01em
- **Body & Prompts**: `Inter`, 13.5px, Weight 400, Line-height 1.45, Letter-spacing -0.005em
- **Telemetry & Numbers**: `JetBrains Mono`, 10.5px, Weight 600, Letter-spacing 0.02em
- **Labels & Microhints**: `JetBrains Mono`, 9.0px, Weight 500, Letter-spacing 0.01em

---

## 4. Spacing System (8pt Modular Grid)

All layout elements align to a strict spatial scale:
- `space-1` = 4px (Micro gaps between icon and text)
- `space-2` = 8px (Pill gaps, button padding, inter-item spacing)
- `space-3` = 12px (Outer window padding, shelf internal gap)
- `space-4` = 16px (Card horizontal padding, modal margin)
- `space-5` = 20px (Section separation)
- `space-6` = 24px (Screen dock margins)
- `space-8` = 32px (Corner boundary radii)

---

## 5. Geometry & Elevation

- **Main Shell**:
  - Idle Dimensions: `440px` width x `184px` height (Logical CSS), `154px` card height.
  - Border Radius: `36px` squircle curvature with radial corner fade mask.
  - Shadow: `0 20px 50px -10px rgba(0,0,0,0.85), 0 0 50px 4px rgba(255,255,255,0.02)`.
  - Backdrop Blur: `backdrop-filter: blur(28px) saturate(180%)`.
- **Token Bar**:
  - Headroom: sits 46px below shell top, protected from top fade.
  - Dimensions: `100%` width x `36px` height.
  - Border: 1px `rgba(255, 255, 255, 0.08)`.
- **Input Pill**:
  - Height: `48px` pill with full `9999px` rounded ends.
  - Fill: `#161618` at 90% opacity.
  - Focus Ring: `1px solid rgba(255, 255, 255, 0.60)`.
- **Active Navigation Tab**:
  - Underline: `2px solid #ffffff`.
  - Background: `rgba(255, 255, 255, 0.08)`.
  - Text: `#ffffff` font-medium.
