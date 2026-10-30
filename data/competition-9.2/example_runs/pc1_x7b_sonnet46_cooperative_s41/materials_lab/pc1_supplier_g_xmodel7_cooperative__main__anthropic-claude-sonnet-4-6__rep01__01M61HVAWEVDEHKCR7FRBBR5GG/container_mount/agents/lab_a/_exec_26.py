
import pandas as pd
df = pd.read_csv('records.csv')

# Check p_GR61XB2TYZ - my primary submission candidate
print("=== p_GR61XB2TYZ (QP-3089 GG7) — PRIMARY CANDIDATE ===")
sub = df[df['prototype_id']=='p_GR61XB2TYZ']
for test, tg in sub.groupby('test'):
    qual = tg[tg['kind']=='qualification']
    print(f"  {test}: {len(qual)}/6  mean={qual['value'].mean():.4f}" if len(qual)>0 else f"  {test}: 0/6")

# Check p_GR61XB2TZA - lab_e backup
print("\n=== p_GR61XB2TZA (QP-3089, lab_e backup) ===")
sub2 = df[df['prototype_id']=='p_GR61XB2TZA']
print(f"  Total records: {len(sub2)}")
for test, tg in sub2.groupby('test'):
    qual = tg[tg['kind']=='qualification']
    print(f"  {test}: {len(qual)}/6  mean={qual['value'].mean():.4f}" if len(qual)>0 else f"  {test}: 0/6")

print("\n=== SUBMISSION READINESS ===")
print("p_GR61XB2TYZ: WAITING FOR WATER PANEL FROM lab_c or lab_f")
print("Thresholds: heat≥78.625°C ✅ 79.281 | strength≥7.235 kN/m ✅ 7.254 | water≥79.8% ❌ MISSING")
print("\nRecord IDs ready to cite:")
print("Heat: r_GR61XB2TZ1, r_GR61XB2TZ2, r_GR61XB2TZ3, r_GR61XB2TZ4, r_GR61XB2TZ5, r_GR61XB2TZ6")
print("Str:  r_QYKNNDRFXJ, r_QYKNNDRFXK, r_QYKNNDRFXM, r_QYKNNDRFXN, r_QYKNNDRFXP, r_QYKNNDRFXQ")
