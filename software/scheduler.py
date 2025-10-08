
# Возвращает часовой пояс из /opt/smart-vent/config/location.yaml
def tz():
    try:
        import yaml
        from zoneinfo import ZoneInfo
        with open("/opt/smart-vent/config/location.yaml","r",encoding="utf-8") as f:
            loc = yaml.safe_load(f)
        return ZoneInfo(loc.get("tz","Asia/Yekaterinburg"))
    except Exception:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Yekaterinburg")
