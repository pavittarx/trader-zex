import reflex as rx
from reflex_base.plugins.sitemap import SitemapPlugin

config = rx.Config(
    app_name="trader_zex",
    plugins=[SitemapPlugin()],
)
