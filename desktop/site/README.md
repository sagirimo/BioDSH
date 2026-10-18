# BioDSH website — Sky edition

Static bilingual landing pages and the interactive asset showroom. English: `/`, Chinese: `/zh/`, showroom: `/brand/?lang=en` or `?lang=zh`.

Edit `build_sky_site.py`, `sky.css`, `sky.js`; run `python build_sky_site.py` to regenerate the two pages. Serve this directory using a static HTTP server. All fonts use system fallbacks. There is no build dependency, analytics or backend connection.

`assets/brand-kit/` mirrors the approved SVGs in `docs/brand/`. The downloadable ZIP contains that complete kit, including React adapters and attribution. Screenshots are clearly labeled design previews. Current installer links point to the verified 0.3.0 release, independently of the asset version `sky-1.0.0`.

Legacy files `build_from_dsref.py`, `finalize_site.py`, `ds.css`, `site.js` and `deploy.sh` are historical. Do not run the old generator or destructive deploy script over this edition. Deploy the new static assets first, back up the existing site, then replace entry HTML files atomically. No server configuration change is required.
