from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/src/crypto/WhatsAppChatExperience.tsx"

REDESIGN_CSS = r"""
      .prepza-wa-shell{
        position:fixed;inset:0;z-index:1000;display:flex;align-items:stretch;justify-content:center;
        background:#dfe3e8;font-family:"Plus Jakarta Sans",system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        color:#172033;
      }
      .prepza-wa-window{
        width:100%;height:100%;display:grid;grid-template-columns:minmax(300px,380px) minmax(0,1fr);
        background:#fff;overflow:hidden;box-shadow:0 22px 70px rgba(8,18,40,.18);
      }
      .prepza-wa-list{display:flex;flex-direction:column;min-width:0;background:#fff;border-right:1px solid #e4e7eb}
      .prepza-wa-list-head{
        min-height:72px;box-sizing:border-box;padding:0 14px;display:flex;align-items:center;gap:8px;
        background:#0b1437;color:#fff;position:relative;
      }
      .prepza-wa-list-head:after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(90deg,transparent,#c9a84c,transparent);opacity:.7}
      .prepza-wa-search{
        margin:10px 12px 8px;height:42px;box-sizing:border-box;display:flex;align-items:center;gap:8px;
        padding:0 12px;border-radius:12px;background:#f1f3f5;border:1px solid #e8eaed;
      }
      .prepza-wa-search input{width:100%;border:0;outline:0;background:transparent;font:inherit;font-size:12px;color:#172033}
      .prepza-wa-row{
        min-height:68px;box-sizing:border-box;margin:2px 8px;padding:9px 9px;display:flex;align-items:center;gap:11px;
        border-radius:14px;cursor:pointer;transition:background .16s,transform .16s;
      }
      .prepza-wa-row:hover{background:#f4f5f7;transform:translateX(1px)}
      .prepza-wa-row:active{transform:scale(.995)}
      .prepza-wa-main{display:flex;flex-direction:column;min-width:0;min-height:0;background:#f1f3f6}
      .prepza-wa-head{
        min-height:68px;box-sizing:border-box;padding:0 14px;display:flex;align-items:center;gap:10px;
        background:#0b1437;color:#fff;border-bottom:1px solid rgba(255,255,255,.07);position:relative;
      }
      .prepza-wa-head:after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;background:rgba(201,168,76,.42)}
      .prepza-wa-messages{
        flex:1;min-height:0;overflow-y:auto;scroll-behavior:smooth;padding:24px max(16px,calc((100vw - 1080px)/2)) 18px;
        background:
          radial-gradient(circle at 15% 20%,rgba(201,168,76,.055),transparent 26%),
          radial-gradient(circle at 82% 76%,rgba(11,20,55,.035),transparent 25%),
          #eef1f4;
      }
      .prepza-wa-messages::-webkit-scrollbar{width:7px}.prepza-wa-messages::-webkit-scrollbar-thumb{background:#c7ccd2;border-radius:99px}
      .prepza-wa-wrap{margin:3px 0 7px;animation:prepzaChatIn .16s ease-out}
      @keyframes prepzaChatIn{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
      .prepza-wa-bubble{
        position:relative;max-width:min(72%,620px);padding:10px 12px 7px;border-radius:17px;margin-bottom:4px;
        box-shadow:0 1px 2px rgba(12,20,35,.08);border:1px solid rgba(17,27,45,.04);
      }
      .prepza-wa-wrap[style*="flex-end"] .prepza-wa-bubble{box-shadow:0 2px 5px rgba(5,14,35,.15)}
      .prepza-wa-actions{position:absolute;top:-28px;right:0;display:flex;gap:4px;opacity:0;pointer-events:none;transition:opacity .15s}
      .prepza-wa-wrap:hover .prepza-wa-actions{opacity:1;pointer-events:auto}
      .prepza-wa-action{border:1px solid #dfe3e8;background:#fff;color:#3c4452;border-radius:9px;padding:5px 8px;font-size:10px;font-weight:750;cursor:pointer;box-shadow:0 3px 10px rgba(0,0,0,.08)}
      .prepza-wa-reactions{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}
      .prepza-wa-reaction{border:1px solid #ded8c5;background:#fff8e7;color:#55420d;border-radius:12px;padding:3px 7px;font-size:11px;cursor:pointer}
      .prepza-wa-composer{
        flex-shrink:0;background:#fff;border-top:1px solid #e1e4e8;padding:10px max(12px,calc((100vw - 1080px)/2)) 13px;
        box-shadow:0 -4px 18px rgba(18,25,38,.035);
      }
      .prepza-wa-attach{
        border:1px solid #e1e4e8;background:#f4f5f7;color:#515968;border-radius:13px;width:40px;height:40px;
        padding:0;cursor:pointer;font-size:18px;transition:.15s;
      }
      .prepza-wa-attach:hover{background:#eceef1}
      .prepza-wa-composer textarea{font-family:"Plus Jakarta Sans",system-ui,sans-serif}
      @media(max-width:900px){.prepza-wa-window{grid-template-columns:320px minmax(0,1fr)}.prepza-wa-bubble{max-width:78%}}
      @media(max-width:760px){
        .prepza-wa-shell{background:#fff}.prepza-wa-window{display:block;position:relative}
        .prepza-wa-list,.prepza-wa-main{width:100%;height:100%;position:absolute;inset:0}
        .prepza-wa-window.detail-mode .prepza-wa-list{display:none}.prepza-wa-window.list-mode .prepza-wa-main{display:none}
        .prepza-wa-list{border-right:0}.prepza-wa-list-head{min-height:64px}.prepza-wa-head{min-height:62px;padding:0 10px}
        .prepza-wa-messages{padding:18px 9px 14px}.prepza-wa-composer{padding:8px 8px 10px}
        .prepza-wa-bubble{max-width:86%;padding:9px 10px 7px}.prepza-wa-actions{opacity:1;pointer-events:auto;position:static;margin:0 0 2px;justify-content:flex-end}
        .prepza-wa-row{min-height:70px;margin:2px 6px;padding:10px 8px;border-radius:13px}
      }
      @media(prefers-color-scheme:dark){
        .prepza-wa-shell{background:#090d16;color:#e8ebf1}
        .prepza-wa-window{background:#111722}.prepza-wa-list{background:#111722;border-color:#242b38}
        .prepza-wa-row:hover{background:#1a2130}.prepza-wa-search{background:#1b2230;border-color:#2a3341}.prepza-wa-search input{color:#eef1f6}
        .prepza-wa-main{background:#0d131e}.prepza-wa-messages{background:radial-gradient(circle at 15% 20%,rgba(201,168,76,.045),transparent 26%),#0f1621}
        .prepza-wa-composer{background:#111722;border-color:#252d39}.prepza-wa-attach{background:#1b2230;border-color:#2b3442;color:#d2d7df}
        .prepza-wa-action{background:#1a2130;border-color:#303948;color:#e6e9ee}.prepza-wa-reaction{background:#2b2514;color:#ead38a;border-color:#5a4a21}
      }
"""

def replace_styles(text: str) -> str:
    pattern = r'<style>\{.*?\}</style>'
    replacement = '<style>{\`' + REDESIGN_CSS + '\`}</style>'
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"CHAT_FRONTEND_REDESIGN_FAILED: expected one style block, found {count}")
    return updated

def remove_exact(text: str, old: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"CHAT_FRONTEND_REDESIGN_FAILED: missing {label}")
    return text.replace(old, "", 1)

def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    text = replace_styles(text)

    ada_row = r'''          <div className="prepza-wa-row" onClick={() => window.dispatchEvent(new CustomEvent('prepza-open-ada'))} style={{ background:'#0b1437',color:'#fff',margin:'10px 10px 6px',borderRadius:13,border:0 }}><div style={{ width:44,height:44,borderRadius:13,background:'rgba(201,168,76,.18)',display:'flex',alignItems:'center',justifyContent:'center',color:'#e4c96a',fontWeight:900 }}>A</div><div style={{ flex:1,minWidth:0 }}><div style={{ fontWeight:850,fontSize:13 }}>Ada</div><div style={{ fontSize:11,opacity:.55 }}>Your study assistant</div></div><span style={{ fontSize:10,color:'#e4c96a' }}>AI</span></div>
'''
    text = remove_exact(text, ada_row, "standalone Ada chat row")

    ada_header = r'''<button type="button" onClick={openAda} aria-label="Study with Ada" style={{ border:'1px solid rgba(201,168,76,.45)',background:'rgba(201,168,76,.12)',color:'#e4c96a',borderRadius:11,padding:'8px 10px',fontWeight:900,fontSize:11,cursor:'pointer' }}>@Ada</button>'''
    text = remove_exact(text, ada_header, "header Ada button")

    ada_composer = r'''<button type="button" onClick={openAda} style={{ height:40,border:'1px solid #dcc67d',borderRadius:12,background:'#fff9e9',color:'#72570e',padding:'0 11px',fontWeight:900,fontSize:11,cursor:'pointer' }}>@Ada</button>'''
    text = remove_exact(text, ada_composer, "composer Ada button")

    TARGET.write_text(text, encoding="utf-8")
    print("CHAT_FRONTEND_REDESIGN_APPLIED")
    print("ADA_STANDALONE_CONTROLS_REMOVED")
    print("ADA_REMAINS_MENTION_DRIVEN")

if __name__ == "__main__":
    main()
