# Python Server

Python 3.11+ package `mdwiki`. FastAPI app under uvicorn, own process, own port. Plus `mdwiki` CLI (`serve`, `validate`, `order`). Deps in `pyproject.toml`: fastapi, uvicorn, markdown, pygments, jinja2, pyyaml.

## File tree

```
pyproject.toml
mdwiki/
  __init__.py          exports serve()
  __main__.py          python -m mdwiki
  cli.py               argparse: serve / validate / order
  config.py            SiteConfig, NavLink, WidgetHook
  link_rewrite.py      InternalLinkExtension
  mermaid.py           MermaidExtension
  ordering.py          _order.yml read/walk/adjacent/edit
  render.py            WikiRenderer, frontmatter, macros, hooks
  server.py            create_app, serve, routes
  validate.py          validate, _check_links
  widgets.py           resolve_widget, widget_markup
  theme/
    __init__.py        DEFAULT_THEME_DIR, STATIC_DIR
tests/
  test_link_rewrite.py
  test_mermaid.py
  test_render.py
  test_static_files.py
```

## How to run

```bash
pip install -e .
mdwiki serve --dir ./example --config ./example/mdwiki.yml --port 8000
mdwiki validate --dir ./example --config ./example/mdwiki.yml
pytest
```

## Features touching this domain

| Feature | Category | Role here |
|---|---|---|
| [Page Routing](../features/Page-Routing.md) | Request Serving | Whole feature. |
| [Page Shell & Asset Serving](../features/Page-Shell-and-Asset-Serving.md) | Request Serving | App factory, routes, template context, CLI launch. |
| [Markdown Rendering](../features/Markdown-Rendering.md) | Content Rendering | Whole feature. |
| [Internal Link Rewriting](../features/Internal-Link-Rewriting.md) | Content Rendering | Whole feature. |
| [Mermaid Diagram Rendering](../features/Mermaid-Diagram-Rendering.md) | Content Rendering | Fence preprocessor, `has_mermaid` flag. |
| [Widget Injection](../features/Widget-Injection.md) | Widget System | Macro/hook placement, resolution, markup, `/_widgets` route. |
| [Standard Widgets](../features/Standard-Widgets.md) | Widget System | `toast` fallback attrs, `next-button` href/label compute. |
| [Page Ordering](../features/Page-Ordering.md) | Site Management | Whole feature. |
| [Site Validation](../features/Site-Validation.md) | Site Management | Whole feature. |
| [Site Configuration Loading](../features/Site-Configuration-Loading.md) | Site Management | Whole feature. |
