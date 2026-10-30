import pandas as pd
r=pd.read_csv('records.csv')
print(r.columns.tolist())
print(r[r['prototype_id'].isin(['p_35M1ZK2VEP','p_BW2PQFB0H1','p_YJ5KCW6SYE','p_YJ5KCW6SY5'])].to_string(index=False))