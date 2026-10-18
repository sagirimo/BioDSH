# BioDSH · Sky identity

晴蓝是 2026-10-18 用户选定的正式品牌方案。此目录是标志与 UI 素材的统一来源。品牌包版本 `sky-1.0.0` 不代表桌面应用版本；配套界面是 1.0 设计预览。

Sky is the approved BioDSH identity. Open `preview/index.html` for the interactive showroom (`?lang=en` for English), or visit the [live showroom](http://43.167.193.205/brand/?lang=en). The desktop release is separate from this asset version.

## Contents

| Directory | Contents |
| --- | --- |
| `brand/` | 12 SVG masters: light/dark wordmarks, rounded/square/small app marks, stacked marks, monochrome wordmarks |
| `icons/` | 48 currentColor SVGs: 28 UI actions, 10 domains, 10 file types |
| `illustrations/` | 8 decorative SVG empty states, 240 × 160 |
| `react/` | BioBrand, BioIcon and semantic mappings; keep brand/ adjacent |
| `png/` | Transparent wordmarks at 512/1024/2048 px; app marks at 16–1024 px; light/dark README banners |
| `tokens.css` | Scoped --bds-* variables for light/dark UI and illustration colors |
| `preview/` | Offline, bilingual, interactive design showroom; all data is illustrative |
| `source/` | Editable geometry, starting outlines and Montserrat OFL attribution |
| `MANIFEST.json` | Asset paths, byte sizes and SHA-256 integrity hashes |

## Color and placement

| Role | Light | Dark |
| --- | --- | --- |
| Bio / primary ink | #0F1115 | #F9FAFB |
| DSH / primary blue | #4176E6 | #7AAAFF |
| Connector / secondary blue | #7AAAFF | #B8D3FF |
| App tile | #F5F6F7 | #151517 |

Use the supplied theme variant. Keep proportions and at least one i-dot diameter of clear space. Use `app-*-small.svg` at 32 px and below. Square masters are for platform masks; do not apply two corner masks. The wordmark contains paths only and needs no installed font. Do not trace the old PNG, add wobble/rotation, recolor individual letters, or stretch the mark.

功能图标使用 `currentColor`，建议 16/20/24/32 px；插图颜色由 `tokens.css` 控制。按钮配本地化名称，状态用文字辅助，来源标记不代表科研验证通过。安装进度、任务完成和分析正确性必须读取各自真实状态。

## React integration

Copy `brand/`, `icons/`, `illustrations/`, `react/`, `tokens.css` together into the app assets directory. BioBrand uses Vite SVG imports. BioIcon is plain JSX with no HTML injection or extra runtime library. Pass resolved light/dark theme, not the settings value `system`.

```tsx
import { BioBrand } from './react/BioBrand';
import { BioIcon } from './react/BioIcon';
<BioBrand variant="app" theme="light" size={40} />
<BioIcon name="ui-skills" size={20} />
```

The preview is not an application backend. Do not copy sample skill counts, progress percentages or success states into product logic. Workflow import/learning buttons require real implemented behavior before enabling them.

## Reuse and provenance

These assets are distributed with BioDSH under the repository license, with the font-derived starting contours additionally covered by `source/OFL.txt`. BioDSH branding must not imply official endorsement of unrelated products. Historical exploration palettes are not part of this approved package. Native icon formats (ICO/ICNS) and application installers must be regenerated and validated during desktop integration; they are not included here.
