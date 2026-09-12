from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
FRONTEND = ROOT / "frontend" / "src" / "App.tsx"


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def patch_app():
    text = APP.read_text()

    old = '''        "maintenance_mode": settings.get("maintenance_mode", "false") == "true",\n        "maintenance_message": settings.get("maintenance_message", ""),'''
    new = '''        "maintenance_mode": settings.get("maintenance_mode", "false") == "true",\n        "maintenance_message": settings.get("maintenance_message", ""),\n        "prepza_control_enabled": settings.get("prepza_control_enabled", "false") == "true",'''
    text = replace_once(text, old, new, "admin settings response")

    old = '''    for price_key in ("price_notes", "price_past_paper", "price_qna", "price_plan_semester", "price_plan_annual"):\n'''
    new = '''    if "prepza_control_enabled" in data:\n        value = data["prepza_control_enabled"]\n        if not isinstance(value, bool):\n            return jsonify({"error": "prepza_control_enabled must be true or false"}), 400\n        setting = SystemSetting.query.filter_by(key="prepza_control_enabled").first()\n        if not setting:\n            setting = SystemSetting(key="prepza_control_enabled", value="false")\n            db.session.add(setting)\n        setting.value = "true" if value else "false"\n        log_admin_action(\n            session.get("user_id"),\n            "control_api_enabled" if value else "control_api_disabled",\n            target_type="control_api",\n            details={"enabled": value},\n        )\n\n    for price_key in ("price_notes", "price_past_paper", "price_qna", "price_plan_semester", "price_plan_annual"):\n'''
    text = replace_once(text, old, new, "admin settings update insertion")

    old = '''    return jsonify({\n        "maintenance_mode": bool(mode_setting and mode_setting.value == "true"),\n        "maintenance_message": message_setting.value if message_setting else "",\n    })\n\n\n# ---------- Organisations (Opportunities + Organisation portal) ----------'''
    new = '''    control_setting = SystemSetting.query.filter_by(key="prepza_control_enabled").first()\n    return jsonify({\n        "maintenance_mode": bool(mode_setting and mode_setting.value == "true"),\n        "maintenance_message": message_setting.value if message_setting else "",\n        "prepza_control_enabled": bool(control_setting and control_setting.value == "true"),\n    })\n\n\n# ---------- Organisations (Opportunities + Organisation portal) ----------'''
    text = replace_once(text, old, new, "admin settings update response")

    old = '''\n\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=5000)\n'''
    new = '''\n\nfrom prepza_control import register_control_routes\n\nregister_control_routes(\n    app,\n    db,\n    SystemSetting,\n    User,\n    Document,\n    DocumentContent,\n    GeneratedMaterial,\n    log_admin_action,\n    limiter,\n)\n\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=5000)\n'''
    text = replace_once(text, old, new, "control route registration")

    APP.write_text(text)


def patch_frontend():
    text = FRONTEND.read_text()

    old = '''type AdminPlatformSettings = {\n  maintenance_mode: boolean\n  maintenance_message: string'''
    new = '''type AdminPlatformSettings = {\n  maintenance_mode: boolean\n  maintenance_message: string\n  prepza_control_enabled: boolean'''
    text = replace_once(text, old, new, "AdminPlatformSettings type")

    old = '''  const savePlatformSettings = async () => {'''
    new = '''  const setPrepzaControlEnabled = async (enabled: boolean) => {\n    if (!settingsDraft || settingsSaving) return\n    if (!enabled && !window.confirm('Disable ChatGPT/Prepza control access now? This immediately blocks all control API requests.')) return\n    setSettingsSaving(true)\n    setSettingsSaveError('')\n    try {\n      await api('/admin/settings', {\n        method: 'PATCH',\n        headers: { 'X-CSRF-Token': csrfToken },\n        body: JSON.stringify({ prepza_control_enabled: enabled }),\n      })\n      await loadPlatformSettings()\n      setSettingsSaved(true)\n    } catch (e) {\n      setSettingsSaveError(e instanceof ApiError ? e.message : 'Could not change control access.')\n    } finally {\n      setSettingsSaving(false)\n    }\n  }\n\n  const savePlatformSettings = async () => {'''
    text = replace_once(text, old, new, "control toggle handler")

    old = '''          </AdminCard>\n\n          <AdminCard title="Content Prices (KES)">'''
    new = '''          </AdminCard>\n\n          <AdminCard title="Prepza Control Access">\n            <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>\n              <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.55 }}>\n                Controls the private developer API used by trusted Prepza tooling. It is disabled by default and still requires a separate server-side token.\n              </div>\n              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>\n                <div>\n                  <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{settingsDraft.prepza_control_enabled ? 'Control access is ON' : 'Control access is OFF'}</div>\n                  <div style={{ fontSize: 11, color: T.textMuted, marginTop: 3 }}>\n                    {settingsDraft.prepza_control_enabled ? 'The API can be reached only with the server-side bearer token.' : 'All control API requests are rejected immediately.'}\n                  </div>\n                </div>\n                <button\n                  onClick={() => setPrepzaControlEnabled(!settingsDraft.prepza_control_enabled)}\n                  disabled={settingsSaving}\n                  style={{ background: settingsDraft.prepza_control_enabled ? '#DC2626' : '#16A34A', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 16px', cursor: settingsSaving ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 12, opacity: settingsSaving ? 0.6 : 1 }}\n                >{settingsSaving ? 'Updating…' : (settingsDraft.prepza_control_enabled ? 'Disable Control Access' : 'Enable Control Access')}</button>\n              </div>\n              <div style={{ fontSize: 11, color: '#92400E', background: '#FEF3C7', borderRadius: 8, padding: '8px 10px' }}>\n                Keep this OFF unless you are actively using the trusted control connection.\n              </div>\n            </div>\n          </AdminCard>\n\n          <AdminCard title="Content Prices (KES)">'''
    text = replace_once(text, old, new, "control settings card")

    FRONTEND.write_text(text)


if __name__ == "__main__":
    patch_app()
    patch_frontend()
    print("Prepza control API and admin kill switch applied.")
