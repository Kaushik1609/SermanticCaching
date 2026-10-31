## Brand & Style

This design system delivers a high-precision, technical infrastructure interface built for machine learning engineers and platform architects. The tone is deliberate, disciplined, and utilitarian—eschewing decorative AI cliches such as purple cosmic gradients, glowing mesh orbs, and anthropomorphic motifs in favor of deterministic clarity and operational confidence.

The design movement combines **Minimalism** with **Modern Developer Tool Architecture**. Information density is prioritized without sacrificing whitespace or optical hierarchy. The interface projects reliability, sub-millisecond precision, and mathematical transparency: semantic distances, vector similarity thresholds, cache hit/miss topologies, and token savings are represented as rigorous telemetry rather than opaque approximations.

## Layout & Spacing

Layout geometry follows an 8pt base grid with a condensed 4pt baseline for dense telemetry readouts and control bars.

- **Structure**: High-density fluid grid anchoring dashboard viewports. The global workspace utilizes a fixed `240px` left rail navigation, a dynamic secondary inspector pane (`360px`–`480px`), and a fluid central console pane with a minimum width threshold of `768px`.
- **Breakpoints**:
  - `Desktop (≥1280px)`: Full multi-pane view (Nav, Telemetry Grid, Split Vector Inspector).
  - `Tablet (768px - 1279px)`: Inspector collapses into a slide-over sheet; metric summary cards compress from 4 to 2 columns.
  - `Mobile (<768px)`: Single column stacking with horizontally scrolling data tables and persistent status breadcrumbs.
- **Rhythm**: Component interiors use dense spacing (`space-sm` to `space-base`), while structural containment uses generous gaps (`space-lg` to `space-xl`) to establish distinct visual modules without visual noise.

## Elevation & Depth

Depth is established primarily through **structural line work and subtle tonal contrasts** rather than deep spatial shadows.

- **Card Level 0 (Canvas)**: Background surface `#F8FAFC` without elevation.
- **Card Level 1 (Base Container)**: `#FFFFFF` surface with a continuous `1px` border of `#E2E8F0` and an ultra-subtle ambient shadow: `0 1px 2px 0 rgba(15, 23, 42, 0.04)`.
- **Card Level 2 (Interactive/Floating Panels)**: `#FFFFFF` surface with a `1px` border of `#CBD5E1` and an elevated shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 2px 4px -2px rgba(15, 23, 42, 0.04)`.
- **Active State / Focus**: No glow effects; focus is communicated via an offset, crisp `2px` focus ring using `#0D9488` at 100% opacity with a `2px` white gap.

## Components

### Buttons
- **Primary**: Solid `#0D9488` surface, `#FFFFFF` Inter 14px semi-bold text, 8px border radius, 0 1px 2px rgba(0, 0, 0, 0.05) shadow. Hover: `#0F766E`. Active: `#115E59`.
- **Secondary / Outline**: `#FFFFFF` surface, `1px solid #E2E8F0`, `#334155` text. Hover: `#F8FAFC` surface, `#CBD5E1` border.
- **Tertiary / Ghost**: Transparent surface, `#475569` text. Hover: `#F1F5F9` background, `#0F172A` text.

### Telemetry Badges & Chips
- **HIT Badge**: `#ECFDF5` background, `#059669` JetBrains Mono 12px text, `1px solid #A7F3D0`. Includes a 6px solid emerald status dot.
- **MISS Badge**: `#FFFBEB` background, `#D97706` JetBrains Mono 12px text, `1px solid #FDE68A`. Includes a 6px solid amber status dot.
- **Similarity Metric Chip**: `#F8FAFC` background, `1px solid #E2E8F0`, displaying threshold equation (`cos θ ≥ 0.88`) with monospace emphasis.

### Cards & Data Panels
- Enclosed within `#FFFFFF` surfaces with `1px solid #E2E8F0` and `12px` border radii.
- Headers feature clear uppercase categorization (`label-caps`) in `#64748B`, metric values in `JetBrains Mono`, and optional secondary actions positioned top-right.

### Form Inputs & Query Testing Console
- Input boxes use `#FFFFFF` fill, `1px solid #CBD5E1`, 8px radius, and Inter 14px body text. Monospace code input boxes for semantic vector testing use `JetBrains Mono 13px` with line numbers and prompt tokens highlighted.
- Focused state applies an immediate `#0D9488` border and `0 0 0 1px #0D9488` crisp shadow ring.

### Data Tables & Log Streamers
- Alternating row interaction: Pure `#FFFFFF` resting state, transitioning to `#F8FAFC` on hover.
- Row separators: Crisp `1px solid #F1F5F9`.
- Column layouts align metadata (Timestamps, Request ID, Latency, Similarity, Cache Decision) into deterministic columns with monospaced values right-aligned for instant visual scanning.

### Semantic Distance Visualizer (Explainability Component)
- Horizontal dual-track bar indicating exact cosine distance between input query and cached embedding.
- Visual threshold indicator: `#0D9488` vertical bar with a monospaced delta readout (`Δ 0.042`).