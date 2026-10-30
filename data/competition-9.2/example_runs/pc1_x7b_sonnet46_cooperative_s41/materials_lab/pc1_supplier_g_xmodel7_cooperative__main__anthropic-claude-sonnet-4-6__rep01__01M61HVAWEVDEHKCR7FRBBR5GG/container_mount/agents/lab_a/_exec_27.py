
import pandas as pd
df = pd.read_csv('records.csv')

# Check p_VZ3XBYF5AW (QP-7212 PL-95)
print("=== p_VZ3XBYF5AW (QP-7212) ===")
sub = df[df['prototype_id']=='p_VZ3XBYF5AW']
print(f"Total records: {len(sub)}")
if len(sub) > 0:
    for test, tg in sub.groupby('test'):
        qual = tg[tg['kind']=='qualification']
        exp = tg[tg['kind']=='exploratory']
        print(f"  {test}: {len(qual)}/6 qual, {len(exp)} exploratory")
        if len(qual) > 0:
            print(f"    Qual mean: {qual['value'].mean():.4f}")
            print(f"    IDs: {qual['record_id'].tolist()}")
        if len(exp) > 0:
            print(f"    Exp mean: {exp['value'].mean():.4f}")

# Check all QP-7212 prototypes
print("\n=== All QP-7212 records ===")
sub2 = df[df['project_id']=='QP-7212']
for pid, tg in sub2.groupby('prototype_id'):
    qual = tg[tg['kind']=='qualification']
    print(f"  {pid}: {len(qual)} qual records across tests")
