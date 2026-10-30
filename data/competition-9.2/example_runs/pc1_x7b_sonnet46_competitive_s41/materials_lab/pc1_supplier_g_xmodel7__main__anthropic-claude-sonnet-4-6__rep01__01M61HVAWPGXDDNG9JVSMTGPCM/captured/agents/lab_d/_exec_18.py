
import pandas as pd
df = pd.read_csv('records.csv')
print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
# Focus on QP-4476 records
qp4 = df[df['project'] == 'QP-4476'].copy()
print(f"\nQP-4476 records: {len(qp4)}")
if len(qp4) > 0:
    # Compute per-prototype mean by test
    grp = qp4.groupby(['prototype_id', 'test'])['value'].agg(['mean','count']).reset_index()
    print(grp.to_string())
print()
# Check p_WEMQRN3Q9M secondary sheet to confirm GG7
w = df[df['prototype_id'] == 'p_WEMQRN3Q9M']
if len(w) > 0:
    print("p_WEMQRN3Q9M secondary_sheet:", w['secondary_sheet'].iloc[0])
    print("Full recipe:", w[['base_sheet','secondary_sheet','binder_system','additive_package_1',
                              'additive_package_2','additive_package_3','process_profile_1',
                              'process_profile_2','process_profile_3','surface_treatment',
                              'joint_system','conditioning_step']].iloc[0].to_dict())
