import streamlit as st
from pathlib import Path
from providers import discover_providers


def _write_config_page(file_path: Path, provider_name: str):
    content = f'''import streamlit as st
from config import AppConfig
from providers import discover_providers

app_config = AppConfig.load()
provider = discover_providers().get({provider_name!r})
if provider:
    config = app_config.get(provider.name)
    provider.config_page(config, app_config)
else:
    st.error(f"供应商未找到: {provider_name!r}")
'''
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


st.set_page_config(page_title="LMHub", page_icon="🧪", layout="wide")

providers = discover_providers()

configs_dir = Path("pages/configs")
configs_dir.mkdir(parents=True, exist_ok=True)

for existing in configs_dir.glob("config_*.py"):
    existing.unlink()

demo_page = st.Page(
    "pages/demo.py", title="Demo", icon="🧪", default=True
)

multi_turn_page = st.Page(
    "pages/multi_turn.py", title="Multi-Turn", icon="🔄"
)


provider_pages = []
for name, provider in providers.items():
    clean_url = "config_" + name.lower().replace(" ", "_").replace(":", "")

    file_path = configs_dir / f"{clean_url}.py"
    _write_config_page(file_path, name)

    page = st.Page(
        str(file_path),
        title=name,
        icon=provider.icon,
        url_path=clean_url,
    )
    provider_pages.append(page)

nav = {
    "🧪 Demo": [demo_page, multi_turn_page],
    "⚙️ Providers": provider_pages,
}

pg = st.navigation(nav)
pg.run()
