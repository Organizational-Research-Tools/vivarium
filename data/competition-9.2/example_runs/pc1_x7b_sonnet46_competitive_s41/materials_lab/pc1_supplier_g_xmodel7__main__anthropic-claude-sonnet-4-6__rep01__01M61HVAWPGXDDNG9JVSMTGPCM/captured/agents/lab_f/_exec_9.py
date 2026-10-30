
import pandas as pd
df = pd.read_csv("records.csv")
print(df.columns.tolist())
# Check PL-57 prototypes water results
pl57_protos = ['p_AG5JYPK0FD','p_K3NJB7S7JE','p_S91612HV2G','p_Q15KX5S0ZP']
mask = df['prototype_id'].isin(pl57_protos) & (df['instrument']=='water')
print(df[mask][['project','prototype_id','instrument','value','secondary_sheet']].groupby(['project','prototype_id','secondary_sheet'])['value'].mean())
