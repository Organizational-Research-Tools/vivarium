
import pandas as pd
df = pd.read_csv('records.csv')

# Check p_GR61XB2TYZ records (QP-3089 GG7)
print("=== p_GR61XB2TYZ (QP-3089 GG7) — current records ===")
sub = df[df['prototype_id']=='p_GR61XB2TYZ']
print(f"Total records: {len(sub)}")
for test, tg in sub.groupby('test'):
    qual = tg[tg['kind']=='qualification']
    print(f"  {test}: {len(qual)}/6 qual, mean={qual['value'].mean():.4f} if {len(qual)}>0")
    if len(qual) > 0:
        print(f"    IDs: {qual['record_id'].tolist()}")

# Check p_8VNBERF1VK (QP-3473 GG7)
print("\n=== p_8VNBERF1VK (QP-3473 GG7) — current records ===")
sub2 = df[df['prototype_id']=='p_8VNBERF1VK']
print(f"Total records: {len(sub2)}")
for test, tg in sub2.groupby('test'):
    qual = tg[tg['kind']=='qualification']
    print(f"  {test}: {len(qual)}/6 qual")

# Summary of what's needed
print("\n=== WHAT'S MISSING ===")
print("p_GR61XB2TYZ (QP-3089 PL-98): Need strength + water panels")
print("p_8VNBERF1VK (QP-3473 PL-95): Need heat + strength + water panels")
print("\nRev C thresholds: heat≥78.625°C, strength≥7.235 kN/m, water≥79.8%")
print("GG7 recipe: P2G/GG7/NN7/57T/LD3/L6C/WB3/P8G/H3F/ZW3/9FU/YV2")
print("Expected performance (from p_GR61XB2TYZ partial data):")
print("  heat: 79.281°C ✅")
