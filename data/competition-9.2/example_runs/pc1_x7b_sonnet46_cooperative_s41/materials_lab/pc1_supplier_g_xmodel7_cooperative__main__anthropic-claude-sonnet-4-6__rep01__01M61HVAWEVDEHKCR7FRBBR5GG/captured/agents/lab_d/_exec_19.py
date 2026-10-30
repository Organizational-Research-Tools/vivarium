
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print()
# Find QP-4476 GG7 recipe panel receipts
q4476_gg7 = df[(df['project_id'] == 'QP-4476') & 
               (df.get('secondary_sheet', df.get('secondary sheet', None)) == 'GG7' 
                if 'secondary_sheet' in df.columns or 'secondary sheet' in df.columns 
                else df['prototype_id'].isin(['p_PXAKTW39C3', 'p_6G7MJ89K4B', 'p_WWXN5W4HZR']))]
print("QP-4476 GG7 records sample:")
print(q4476_gg7[['record_id','prototype_id','instrument','kind','value']].to_string())
