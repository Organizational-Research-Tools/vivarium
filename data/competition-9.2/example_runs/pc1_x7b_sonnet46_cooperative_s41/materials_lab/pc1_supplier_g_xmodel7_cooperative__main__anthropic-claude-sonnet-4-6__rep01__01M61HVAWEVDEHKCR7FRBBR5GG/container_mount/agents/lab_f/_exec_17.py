
import pandas as pd
df = pd.read_csv('records.csv')

# Check recipes of best-strength prototypes and QP-4476 pending prototypes
modules = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
           'additive_package_2','additive_package_3','process_profile_1',
           'process_profile_2','process_profile_3','surface_treatment',
           'joint_system','conditioning_step']

# Best non-GG7 strength prototype
best_str = df[df['prototype_id']=='p_1JB4S9JBGQ'].dropna(subset=['base_sheet']).head(1)
if len(best_str)>0:
    print("p_1JB4S9JBGQ recipe:", list(best_str[modules].values[0]))
else:
    print("p_1JB4S9JBGQ: recipe unknown")

# Also check p_ED8BM3M168 (80.05% water on QP-3089)
ed = df[df['prototype_id']=='p_ED8BM3M168'].dropna(subset=['base_sheet']).head(1)
if len(ed)>0:
    print("p_ED8BM3M168 recipe:", list(ed[modules].values[0]))
else:
    print("p_ED8BM3M168: recipe unknown")

# p_8JDCVCZNMF (81.2% water on QP-7212)
mf = df[df['prototype_id']=='p_8JDCVCZNMF'].dropna(subset=['base_sheet']).head(1)
if len(mf)>0:
    print("p_8JDCVCZNMF recipe:", list(mf[modules].values[0]))
else:
    print("p_8JDCVCZNMF: recipe unknown")

# Check compositions of the pending QP-4476 prototypes
for pid in ['p_21XPKFZDE3','p_8209SDK7SY','p_QRWFK58BS5']:
    row = df[df['prototype_id']==pid].dropna(subset=['base_sheet']).head(1)
    if len(row)>0:
        print(f"{pid} recipe: {list(row[modules].values[0])}")
    else:
        print(f"{pid}: recipe unknown")

# GR61XB2TZA - the one with strength 7.254 (only Rev C passer)
gz = df[df['prototype_id']=='p_GR61XB2TZA'].dropna(subset=['base_sheet']).head(1)
if len(gz)>0:
    print("p_GR61XB2TZA recipe:", list(gz[modules].values[0]))
else:
    print("p_GR61XB2TZA: recipe unknown")
