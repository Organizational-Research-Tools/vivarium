import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
r = df[df.get('project_id', pd.Series(['']*len(df)))=='QP-4069'] if 'project_id' in df.columns else df
# just filter rows mentioning receipts of interest
import re
for rec in ['r_772109W9KC','r_36ENPZEFDV','r_QSWQEK3397']:
    m = df[df.apply(lambda row: rec in str(row.values), axis=1)]
    print(rec, len(m))
print(df.tail(5).to_string())