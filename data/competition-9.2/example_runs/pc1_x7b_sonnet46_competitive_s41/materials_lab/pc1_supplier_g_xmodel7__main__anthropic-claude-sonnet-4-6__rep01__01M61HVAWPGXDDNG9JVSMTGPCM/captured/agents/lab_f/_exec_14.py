
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print()

# Check for p_BNV031NMS0 and p_KM74HN14JP
targets = ['p_BNV031NMS0', 'p_KM74HN14JP']
for t in targets:
    sub = df[df['prototype_id'] == t]
    print(f"Prototype {t}: {len(sub)} records")
    if len(sub) > 0:
        print(sub[['record_id','prototype_id','project','instrument','kind','value']].to_string())
    print()

# All QP-6843 water records
print("=== All QP-6843 water records ===")
sub6843 = df[(df['project']=='QP-6843') & (df['instrument']=='water')]
print(sub6843[['record_id','prototype_id','kind','value']].to_string())
print()

# All QP-4476 water records
print("=== All QP-4476 water records ===")
sub4476 = df[(df['project']=='QP-4476') & (df['instrument']=='water')]
print(sub4476[['record_id','prototype_id','kind','value']].to_string())
print()

# Check all projects and their water records
print("=== Prototype counts by project ===")
print(df.groupby(['project','instrument','kind'])['prototype_id'].nunique())
