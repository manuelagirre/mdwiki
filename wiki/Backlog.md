# Backlog

Items added by `/backlog-new-item`, not by `/wiki-init`.

## Items

- [Load Widgets Only From Repo Widgets Dir](backlog-items/Load-Widgets-Only-From-Repo-Widgets-Dir.md) — widgets_dir: in mdwiki.yml is only host widget source; drop --widgets (deprecate first) and env sources; repo override of built-in allowed, reported by validate
- [Hide Gitignored And Configured Paths From Site](backlog-items/Hide-Gitignored-And-Configured-Paths-From-Site.md) — honour .gitignore with own matcher (git as test oracle); hide rules negotiable in mdwiki.yml except .git/ and mdwiki.yml; validate reports what is hidden
- [Fix Widget Placeholder Sentinel Collision](backlog-items/Fix-Widget-Placeholder-Sentinel-Collision.md) — page text spelling internal widget sentinel 500s or gets forged widget; per-render nonce sentinel

## Closed / superseded

- Serve Author HTML And Static Files — shipped; folded into [Page Routing](features/Page-Routing.md)'s Code Elements, Process Flow, Use Cases (UC8, new UC10), Fragility Points; [Site Validation](features/Site-Validation.md)'s UC4, new UC6, Fragility Points; [Page Shell & Asset Serving](features/Page-Shell-and-Asset-Serving.md)'s `_page` route; [Internal Link Rewriting](features/Internal-Link-Rewriting.md)'s UC4. No external doc (user opted out).
