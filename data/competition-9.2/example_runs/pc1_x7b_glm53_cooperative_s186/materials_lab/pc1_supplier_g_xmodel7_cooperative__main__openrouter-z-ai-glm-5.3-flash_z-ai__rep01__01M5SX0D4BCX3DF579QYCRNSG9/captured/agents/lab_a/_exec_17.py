import pandas as pd
df = pd.read_csv('records.csv')
q = df[df.project=='QP-8476']
# any T3M anywhere? composition of QP-4069/5993/4757 rows
other = df[df.project.isin(['QP-4069','QP-5993','QP-4757'])]
print(other.groupby(['project','test'])['value'].agg(['mean','max','count']))
print('T3M secondary rows overall:', (df.secondary_sheet=='T3M').sum())
print(df[df.secondary_sheet=='T3M'].groupby(['project','test'])['value'].agg(['mean','count']))