import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config/tapstats/config.toml"


@dataclass
class DaemonConfig:
    tick_interval: float = 1.0
    flush_interval: float = 30.0


@dataclass
class WaybarConfig:
    signal: int = 8
    top_keys_count: int = 5
    display: str = "keyboard"  # "keyboard", "mouse", "both"
    compact: bool = True


@dataclass
class PanelConfig:
    history_days: int = 14


@dataclass
class DbConfig:
    path: str = "~/.local/share/tapstats/stats.db"


@dataclass
class Config:
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    waybar: WaybarConfig = field(default_factory=WaybarConfig)
    panel: PanelConfig = field(default_factory=PanelConfig)
    db: DbConfig = field(default_factory=DbConfig)


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = _load()
    return _config


def _load() -> Config:
    cfg = Config()
    if not CONFIG_PATH.exists():
        return cfg
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    if d := data.get("daemon"):
        cfg.daemon.tick_interval = d.get("tick_interval", cfg.daemon.tick_interval)
        cfg.daemon.flush_interval = d.get("flush_interval", cfg.daemon.flush_interval)
    if w := data.get("waybar"):
        cfg.waybar.signal = w.get("signal", cfg.waybar.signal)
        cfg.waybar.top_keys_count = w.get("top_keys_count", cfg.waybar.top_keys_count)
        cfg.waybar.display = w.get("display", cfg.waybar.display)
        cfg.waybar.compact = w.get("compact", cfg.waybar.compact)
    if p := data.get("panel"):
        cfg.panel.history_days = p.get("history_days", cfg.panel.history_days)
    if db := data.get("db"):
        cfg.db.path = db.get("path", cfg.db.path)
    return cfg
