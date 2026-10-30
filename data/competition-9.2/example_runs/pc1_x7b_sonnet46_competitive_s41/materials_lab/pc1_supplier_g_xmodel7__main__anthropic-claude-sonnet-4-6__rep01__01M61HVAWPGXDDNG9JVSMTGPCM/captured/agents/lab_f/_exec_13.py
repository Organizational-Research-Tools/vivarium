
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print("Total records:", len(df))
print()

# Check for p_BNV031NMS0 and p_KM74HN14JP
targets = ['p_BNV031NMS0', 'p_KM74HN14JP']
for t in targets:
    sub = df[df['prototype_id'] == t]
    print(f"Prototype {t}: {len(sub)} records")
    if len(sub) > 0:
        print(sub[['record_id','prototype_id','project_id','instrument','kind','value']].to_string())
    print()

# Check lab_d's QP-4476 prototypes
d_protos = ['p_WEMQRN3Q9M', 'p_X9WN43AQ4V', 'p_X9WN43AQ4X']
for p in d_protos:
    sub = df[df['prototype_id'] == p]
    print(f"Prototype {p}: {len(sub)} records")
    if len(sub) > 0:
        print(sub[['record_id','prototype_id','project_id','instrument','kind','value']].to_string())
    print()

# Check all QP-4476 water records
print("=== All QP-4476 water records ===")
sub = df[(df['project_id']=='QP-4476') & (df['instrument']=='water')]
print(sub[['record_id','prototype_id','kind','value']].to_string())
