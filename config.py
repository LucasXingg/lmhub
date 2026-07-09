import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("configs/app_config.json")


@dataclass
class ProviderConfig:
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderConfig":
        return cls(
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 4096),
            extra=data.get("extra", {}),
        )


@dataclass
class AppConfig:
    providers: dict[str, dict[str, ProviderConfig]] = field(default_factory=dict)

    def get(self, name: str) -> ProviderConfig:
        profiles = self.providers.get(name, {})
        if not profiles:
            return ProviderConfig()
        return list(profiles.values())[0]

    def get_profile(self, name: str, profile: str) -> ProviderConfig:
        if name not in self.providers:
            self.providers[name] = {}
        if profile not in self.providers[name]:
            self.providers[name][profile] = ProviderConfig()
        return self.providers[name][profile]

    def list_profiles(self, name: str) -> list[str]:
        return list(self.providers.get(name, {}).keys())

    def delete_profile(self, name: str, profile: str):
        if name in self.providers and profile in self.providers[name]:
            del self.providers[name][profile]

    def clone_profile(self, name: str, source: str, target: str):
        src = self.get_profile(name, source)
        self.providers.setdefault(name, {})[target] = ProviderConfig.from_dict(
            src.to_dict()
        )

    def rename_profile(self, name: str, old: str, new: str):
        if name in self.providers and old in self.providers[name]:
            self.providers[name][new] = self.providers[name].pop(old)

    def to_dict(self) -> dict:
        return {
            "providers": {
                name: {p: c.to_dict() for p, c in profiles.items()}
                for name, profiles in self.providers.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        providers_data = data.get("providers", {})
        providers = {}
        for name, value in providers_data.items():
            if "api_key" in value:
                providers[name] = {"默认": ProviderConfig.from_dict(value)}
            else:
                providers[name] = {
                    p: ProviderConfig.from_dict(c) for p, c in value.items()
                }
        return cls(providers=providers)

    def save(self, path: str | Path = DEFAULT_CONFIG_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "AppConfig":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return cls()
