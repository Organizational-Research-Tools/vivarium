
import pandas as pd

df = pd.read_csv('records.csv')

# Cross-reference: which QP-4476 prototypes have data on which instruments?
print("=== QP-4476 coverage by prototype ===")
q4476 = df[df['project']=='QP-4476']
cov = q4476.groupby(['prototype_id','instrument','kind'])['value'].agg(['mean','count']).reset_index()
print(cov.to_string(index=False))

print("\n=== QP-7212 coverage by prototype ===")
q7212 = df[df['project']=='QP-7212']
cov2 = q7212.groupby(['prototype_id','instrument','kind'])['value'].agg(['mean','count']).reset_index()
print(cov2.to_string(index=False))

print("\n=== QP-3089 coverage by prototype ===")
q3089 = df[df['project']=='QP-3089']
cov3 = q3089.groupby(['prototype_id','instrument','kind'])['value'].agg(['mean','count']).reset_index()
print(cov3.to_string(index=False))

print("\n=== QP-3473 coverage by prototype ===")
q3473 = df[df['project']=='QP-3473']
cov4 = q3473.groupby(['prototype_id','instrument','kind'])['value'].agg(['mean','count']).reset_index()
print(cov4.to_string(index=False))
