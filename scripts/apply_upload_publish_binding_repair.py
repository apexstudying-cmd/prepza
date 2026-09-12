from pathlib import Path

p = Path("frontend/src/App.tsx")
s = p.read_text()

step2 = '''      {/* Step 2: Details */}
      {step === 2 && (
'''
step2_button = '''          <button onClick={() => canProceed2 && setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            {selectedDoc?.status === 'ready' ? 'Continue' : 'Document still preparing…'}
          </button>
'''
step2_button_clean = '''          <button onClick={() => canProceed2 && setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            Continue
          </button>
'''
if step2 not in s:
    raise SystemExit("Step 2 marker not found")
step2_start = s.index(step2)
step3_start = s.index("      {/* Step 3: Rights confirmation */}", step2_start)
step2_block = s[step2_start:step3_start]
if step2_button in step2_block:
    step2_block = step2_block.replace(step2_button, step2_button_clean, 1)
    s = s[:step2_start] + step2_block + s[step3_start:]

# Normalize the Step 1 control so it stays tied to the selected uploaded document's readiness.
step1 = '''      {/* Step 1: Select doc + title */}
      {step === 1 && (
'''
step1_start = s.index(step1)
step2_start = s.index("      {/* Step 2: Details */}", step1_start)
step1_block = s[step1_start:step2_start]
step1_old = '''          <button onClick={() => canProceed1 && setStep(2)} style={{ width: '100%', background: canProceed1 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed1 ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed1 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>
            Continue
          </button>
'''
step1_new = '''          <button onClick={() => canProceed1 && setStep(2)} disabled={!canProceed1} style={{ width: '100%', background: canProceed1 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed1 ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed1 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>
            {selectedDoc?.status === 'ready' ? 'Continue' : 'Document still preparing…'}
          </button>
'''
if step1_old in step1_block:
    step1_block = step1_block.replace(step1_old, step1_new, 1)
    s = s[:step1_start] + step1_block + s[step2_start:]

p.write_text(s)
print("Library publishing control normalization applied")
